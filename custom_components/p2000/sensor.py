"""Support for P2000 sensors."""
import datetime
import logging

import feedparser
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RADIUS,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
import homeassistant.util as util
from homeassistant.util import Throttle
from homeassistant.util.location import distance

BASE_URL = "https://feeds.livep2000.nl?r={}&d={}"
_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=10)

CONF_REGIOS = "regios"
CONF_DISCIPLINES = "disciplines"
CONF_CAPCODES = "capcodes"
CONF_ATTRIBUTION = "Data provided by feeds.livep2000.nl"
CONF_NOLOCATION = "nolocation"

DEFAULT_NAME = "P2000"
ICON = "mdi:ambulance"
DEFAULT_DISCIPLINES = "1,2,3,4"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_REGIOS): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_DISCIPLINES, default=DEFAULT_DISCIPLINES): cv.string,
        vol.Optional(CONF_RADIUS, 0): vol.Coerce(float),
        vol.Optional(CONF_CAPCODES): cv.string,
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
        vol.Optional(CONF_NOLOCATION, default=False): cv.boolean,
    }
)


async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up the P2000 sensor."""
    data = P2000Data(hass, config)

    try:
        await data.async_update()
    except ValueError as err:
        _LOGGER.error("Error while fetching P2000 feed: %s", err)
        return

    async_add_devices([P2000Sensor(data, config.get(CONF_NAME))], True)


class P2000Data:
    """Handle P2000 object and limit updates."""

    def __init__(self, hass, config):
        """Initialize the data object."""
        self._hass = hass
        self._lat = util.convert(config.get(CONF_LATITUDE, hass.config.latitude), float)
        self._lon = util.convert(
            config.get(CONF_LONGITUDE, hass.config.longitude), float
        )
        self._url = BASE_URL.format(
            config.get(CONF_REGIOS), config.get(CONF_DISCIPLINES)
        )
        self._nolocation = config.get(CONF_NOLOCATION)
        self._radius = config.get(CONF_RADIUS)
        self._capcodes = config.get(CONF_CAPCODES)
        self._capcodelist = None
        self._feed = None
        self._etag = None
        self._modfied = None
        self._lastmsg_time = None
        self._restart = True
        self._data = None

        if self._capcodes:
            self._capcodelist = self._capcodes.split(",")

    @property
    def latest_data(self):
        """Return the latest data object."""
        if self._data:
            return self._data
        return None

    @staticmethod
    def _convert_time(time):
        return datetime.datetime.strptime(time.split(",")[1][:-6], " %d %b %Y %H:%M:%S")

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Update data."""
        _LOGGER.debug("Feed URL: %s", self._url)

        if self._feed:
            self._modified = self._feed.get("modified")
            self._etag = self._feed.get("etag")
        else:
            self._modified = None
            self._etag = None

        try:
            self._feed = await self._hass.async_add_executor_job(feedparser.parse,
                self._url, self._etag, self._modfied
            )
            _LOGGER.debug("Feed contents: %s", self._feed)

            if not self._feed:
                _LOGGER.debug("Failed to get feed")
            else:
                if self._feed.bozo != 0:
                    _LOGGER.debug("Error parsing feed %s", self._url)
                elif len(self._feed.entries) > 0:
                    _LOGGER.debug("Got %s entries", len(self._feed.entries))

                    pubdate = self._feed.entries[0]["published"]

                    if self._restart:
                        self._lastmsg_time = self._convert_time(pubdate)
                        self._restart = False
                        _LOGGER.debug("Last datestamp read %s", self._lastmsg_time)
                        return

                    for item in reversed(self._feed.entries):
                        eventmsg = ""

                        lastmsg_time = self._convert_time(item.published)
                        if lastmsg_time < self._lastmsg_time:
                            continue
                        self._lastmsg_time = lastmsg_time

                        eventmsg = item.title.replace("~", "") + "\n" + item.published + "\n"
                        _LOGGER.debug("New emergency event found: %s", eventmsg)

                        if "geo_lat" in item:
                            lat_event = float(item.geo_lat)
                            lon_event = float(item.geo_long)
                            dist = distance(self._lat, self._lon, lat_event, lon_event)
                            if self._radius:
                                _LOGGER.debug("Filtering on Radius %s", self._radius)
                                _LOGGER.debug("Calculated distance %d m", dist)
                                if dist > self._radius:
                                    eventmsg = ""
                                    _LOGGER.debug("Radius filter mismatch")
                                    continue
                                else:
                                    _LOGGER.debug("Radius filter matched")
                        else:
                            _LOGGER.debug("No location info in item")
                            lat_event = 0.0
                            lon_event = 0.0
                            dist = 0
                            if not self._nolocation:
                                _LOGGER.debug("No location, discarding.")
                                eventmsg = ""
                                continue

                        if "summary" in item:
                            capcodetext = item.summary.replace("<br />", "\n")
                        else:
                            capcodetext = ""

                        if self._capcodelist:
                            _LOGGER.debug(
                                "Filtering on Capcode(s) %s", self._capcodelist
                            )
                            capfound = False
                            for capcode in self._capcodelist:
                                _LOGGER.debug(
                                    "Searching for capcode %s in %s",
                                    capcode.strip(),
                                    capcodetext,
                                )
                                if capcodetext.find(capcode) != -1:
                                    _LOGGER.debug("Capcode filter matched")
                                    capfound = True
                                    break
                                else:
                                    _LOGGER.debug("Capcode filter mismatch")
                                    continue
                            if not capfound:
                                eventmsg = ""

                        if eventmsg:
                            event = {}
                            event["msgtext"] = eventmsg
                            event["latitude"] = lat_event
                            event["longitude"] = lon_event
                            event["distance"] = int(round(dist))
                            event["msgtime"] = lastmsg_time
                            event["capcodetext"] = capcodetext
                            _LOGGER.debug(
                                "Text: %s, Time: %s, Lat: %s, Long: %s, Distance: %s, Capcodetest: %s",
                                event["msgtext"],
                                event["msgtime"],
                                event["latitude"],
                                event["longitude"],
                                event["distance"],
                                event["capcodetext"],
                            )
                            self._data = event

        except ValueError as err:
            _LOGGER.error("Error feedparser %s", err.args)
            self._data = None


class P2000Sensor(Entity):
    """Representation of a P2000 Sensor."""

    def __init__(self, data, name):
        """Initialize a P2000 sensor."""
        self._data = data
        self._name = name
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return ICON

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        attrs = {}
        data = self._data.latest_data
        if data:
            attrs[ATTR_LONGITUDE] = data["longitude"]
            attrs[ATTR_LATITUDE] = data["latitude"]
            attrs["distance"] = data["distance"]
            attrs["capcodes"] = data["capcodetext"]
            attrs["time"] = data["msgtime"]
            attrs[ATTR_ATTRIBUTION] = CONF_ATTRIBUTION
        return attrs

    async def async_update(self):
        """Update current values."""
        await self._data.async_update()
        data = self._data.latest_data
        if data:
            self._state = data["msgtext"]
            _LOGGER.debug("State updated to %s", self._state)
