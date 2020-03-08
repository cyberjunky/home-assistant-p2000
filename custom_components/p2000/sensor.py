import datetime
import logging

import feedparser
from geopy.distance import vincenty
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

BASE_URL = "https://feeds.livep2000.nl?r={}&d={}"
_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=10)

CONF_REGIOS = "regios"
CONF_DISCIPLINES = "disciplines"
CONF_CAPCODES = "capcodes"
CONF_ATTRIBUTION = "Data provided by feeds.livep2000.nl"

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
        self._lat = util.convert(config.get(CONF_LATITUDE, hass.config.latitude), float)
        self._lon = util.convert(
            config.get(CONF_LONGITUDE, hass.config.longitude), float
        )
        self._url = BASE_URL.format(
            config.get(CONF_REGIOS), config.get(CONF_DISCIPLINES)
        )
        self._radius = config.get(CONF_RADIUS)
        self._capcodes = config.get(CONF_CAPCODES)
        self._capcodelist = None
        self._feed = None
        self._lastmsg_time = None
        self._restart = True
        self._matched = False
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
        _LOGGER.debug("Fetch URL: %s", self._url)
        self._matched = False
        events = []
        lat_event = 0.0
        lon_event = 0.0
        try:
            self._feed = feedparser.parse(
                self._url,
                etag=None if not self._feed else self._feed.get("etag"),
                modified=None if not self._feed else self._feed.get("modified"),
            )
            _LOGGER.debug("Fetched data = %s", self._feed)

            if not self._feed:
                _LOGGER.debug("Failed to get data from feed")
            else:
                if self._feed.bozo != 0:
                    _LOGGER.debug("Error parsing feed %s", self._url)
                elif len(self._feed.entries) > 0:
                    _LOGGER.debug("%s entries downloaded", len(self._feed.entries))

                    if self._restart:
                        pubdate = self._feed.entries[0]["published"]
                        self._lastmsg_time = self._convert_time(pubdate)
                        self._restart = False
                        _LOGGER.debug("Last datestamp read %s", self._lastmsg_time)
                        return

                    for item in reversed(self._feed.entries):
                        lat_event = 0.0
                        lon_event = 0.0
                        dist = 0
                        capcodetext = ""
                        self._matched = False

                        if "published" in item:
                            pubdate = item.published
                            lastmsg_time = self._convert_time(pubdate)

                        if lastmsg_time < self._lastmsg_time:
                            continue

                        _LOGGER.debug("New emergency event found.")
                        _LOGGER.debug(item.title.replace("~", "") + "\n" + pubdate + "\n"
                                )
                        self._lastmsg_time = lastmsg_time

                        if "geo_lat" in item:
                            lat_event = float(item.geo_lat)
                        else:
                            continue

                        if "geo_long" in item:
                            lon_event = float(item.geo_long)
                        else:
                            continue

                        if lat_event and lon_event:
                            dist = vincenty((self._lat, self._lon), (lat_event, lon_event)).meters

                            msgtext = (
                                item.title.replace("~", "") + "\n" + pubdate + "\n"
                            )
                            _LOGGER.debug(
                                "Calculated distance %d meters, max. range %d meters",
                                dist,
                                self._radius,
                            )

                        if self._radius:
                            if dist > self._radius:
                                self._matched = False
                                _LOGGER.debug("Outside range")
                                continue
                            else:
                                self._matched = True
                                _LOGGER.debug("Inside range")

                        if "summary" in item:
                            capcodetext = item.summary.replace("<br />", "\n")

                            if self._capcodelist:
                                for capcode in self._capcodelist:
                                    _LOGGER.debug(
                                        "Searching for capcode %s in %s",
                                        capcode.strip(),
                                        capcodetext,
                                    )
                                    if capcodetext.find(capcode) != -1:
                                        _LOGGER.debug("Found capcode %s", capcode)
                                        self._matched = True
                                    else:
                                        _LOGGER.debug(
                                            "Didn't find capcode %s, skip.", capcode
                                        )
                                        continue

                if self._matched:
                    event = {}
                    event["msgtext"] = msgtext
                    event["latitude"] = lat_event
                    event["longitude"] = lon_event
                    event["distance"] = int(round(dist))
                    event["msgtime"] = lastmsg_time
                    event["capcodetext"] = capcodetext
                    _LOGGER.debug(
                        "Text: %s, Time: %s, Lat: %s, Long: %s, Distance: %s",
                        event["msgtext"],
                        event["msgtime"],
                        event["latitude"],
                        event["longitude"],
                        event["distance"],
                    )
                    events.append(event)
                    self._data = events

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
            for event in data:
                attrs[ATTR_LONGITUDE] = event["longitude"]
                attrs[ATTR_LATITUDE] = event["latitude"]
                attrs["distance"] = event["distance"]
                attrs["capcodes"] = event["capcodetext"]
                attrs["time"] = event["msgtime"]
                attrs[ATTR_ATTRIBUTION] = CONF_ATTRIBUTION
        return attrs

    async def async_update(self):
        """Update current values."""
        await self._data.async_update()
        data = self._data.latest_data
        if data:
            for event in data:
                self._state = event["msgtext"]
                _LOGGER.debug("State updated to %s", self._state)
