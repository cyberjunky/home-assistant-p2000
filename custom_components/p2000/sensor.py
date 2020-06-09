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
    CONF_SCAN_INTERVAL,
    CONF_ICON,
)
from homeassistant.core import callback
import homeassistant.util as util
from homeassistant.util.location import distance
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.restore_state import RestoreEntity

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://feeds.livep2000.nl?r={}&d={}"

DEFAULT_INTERVAL = datetime.timedelta(seconds=10)
DATA_UPDATED = "p2000_data_updated"

CONF_REGIOS = "regios"
CONF_DISCIPLINES = "disciplines"
CONF_CAPCODES = "capcodes"
CONF_ATTRIBUTION = "Data provided by feeds.livep2000.nl"
CONF_NOLOCATION = "nolocation"
CONF_CONTAINS = "contains"

DEFAULT_NAME = "P2000"
DEFAULT_ICON = "mdi:ambulance"
DEFAULT_DISCIPLINES = "1,2,3,4"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_REGIOS): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_DISCIPLINES, default=DEFAULT_DISCIPLINES): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_INTERVAL): vol.All(
                    cv.time_period, cv.positive_timedelta
                ),
        vol.Optional(CONF_RADIUS, 0): vol.Coerce(float),
        vol.Optional(CONF_CAPCODES): cv.string,
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
        vol.Optional(CONF_NOLOCATION, default=False): cv.boolean,
        vol.Optional(CONF_CONTAINS): cv.string,
        vol.Optional(CONF_ICON, default=DEFAULT_ICON): cv.icon,
    }
)


async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up the P2000 sensor."""
    data = P2000Data(hass, config)

    async_track_time_interval(hass, data.async_update, config[CONF_SCAN_INTERVAL])

    async_add_devices([P2000Sensor(hass, data, config.get(CONF_NAME), config.get(CONF_ICON))], True)


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
        self._contains = config.get(CONF_CONTAINS)
        self._capcodelist = None
        self._feed = None
        self._etag = None
        self._modified = None
        self._restart = True
        self._event_time = None
        self._data = None

        if self._capcodes:
            self._capcodelist = self._capcodes.split(",")

    @property
    def latest_data(self):
        """Return the data object."""
        return self._data

    @staticmethod
    def _convert_time(time):
        return datetime.datetime.strptime(time.split(",")[1][:-6], " %d %b %Y %H:%M:%S")

    async def async_update(self, dummy):
        """Update data."""

        if self._feed:
            self._modified = self._feed.get("modified")
            self._etag = self._feed.get("etag")
        else:
            self._modified = None
            self._etag = None

        self._feed = await self._hass.async_add_executor_job(
            feedparser.parse, self._url, self._etag, self._modified
        )

        if not self._feed:
            _LOGGER.debug("Failed to get feed data from %s", self._url)
            return

        if self._feed.bozo:
            _LOGGER.debug("Error parsing feed data from %s", self._url)
            return

        _LOGGER.debug("Feed url: %s data: %s", self._url, self._feed)

        if self._restart:
            self._restart = False
            self._event_time = self._convert_time(self._feed.entries[0]["published"])
            _LOGGER.debug("Start fresh after a restart")
            return

        try:
            for entry in reversed(self._feed.entries):

                event_msg = ""
                event_caps = ""
                event_time = self._convert_time(entry.published)
                if event_time < self._event_time:
                    continue
                self._event_time = event_time
                event_msg = entry.title.replace("~", "") + "\n" + entry.published + "\n"
                _LOGGER.debug("New P2000 event found: %s, at %s", event_msg, entry.published)

                if "geo_lat" in entry:
                    event_lat = float(entry.geo_lat)
                    event_lon = float(entry.geo_long)
                    event_dist = distance(self._lat, self._lon, event_lat, event_lon)
                    event_dist = int(round(event_dist))
                    if self._radius:
                        _LOGGER.debug(
                            "Filtering on Radius %s, calculated distance %d m ",
                            self._radius,
                            event_dist,
                        )
                        if event_dist > self._radius:
                            event_msg = ""
                            _LOGGER.debug("Radius filter mismatch, discarding")
                            continue
                        _LOGGER.debug("Radius filter matched")
                else:
                    event_lat = 0.0
                    event_lon = 0.0
                    event_dist = 0
                    if not self._nolocation:
                        _LOGGER.debug("No location found, discarding")
                        continue

                if "summary" in entry:
                    event_caps = entry.summary.replace("<br />", "\n")

                if self._capcodelist:
                    _LOGGER.debug("Filtering on Capcode(s) %s", self._capcodelist)
                    capfound = False
                    for capcode in self._capcodelist:
                        _LOGGER.debug(
                            "Searching for capcode %s in %s", capcode.strip(), event_caps,
                        )
                        if event_caps.find(capcode) != -1:
                            _LOGGER.debug("Capcode filter matched")
                            capfound = True
                            break
                        _LOGGER.debug("Capcode filter mismatch, discarding")
                        continue
                    if not capfound:
                        continue

                if self._contains:
                    _LOGGER.debug("Filtering on Contains string %s", self._contains)
                    if event_msg.find(self._contains) != -1:
                        _LOGGER.debug("Contains string filter matched")
                    else:
                        _LOGGER.debug("Contains string filter mismatch, discarding")
                        continue

                if event_msg:
                    event = {}
                    event["msgtext"] = event_msg
                    event["latitude"] = event_lat
                    event["longitude"] = event_lon
                    event["distance"] = event_dist
                    event["msgtime"] = event_time
                    event["capcodetext"] = event_caps
                    _LOGGER.debug("Event: %s", event)
                    self._data = event

            dispatcher_send(self._hass, DATA_UPDATED)

        except ValueError as err:
            _LOGGER.error("Error parsing feed data %s", err)
            self._data = None


class P2000Sensor(RestoreEntity):
    """Representation of a P2000 Sensor."""

    def __init__(self, hass, data, name, icon):
        """Initialize a P2000 sensor."""
        self._hass = hass
        self._data = data
        self._name = name
        self._icon = icon
        self._state = None
        self.attrs = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return self._icon

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def should_poll(self):
        """Return the polling requirement for this sensor."""
        return False

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if not state:
            return
        self._state = state.state
        self.attrs = state.attributes

        async_dispatcher_connect(
            self._hass, DATA_UPDATED, self._schedule_immediate_update
        )

    @callback
    def _schedule_immediate_update(self):
        self.async_schedule_update_ha_state(True)

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
            self.attrs = attrs

        return self.attrs

    def update(self):
        """Update current values."""
        data = self._data.latest_data
        if data:
            self._state = data["msgtext"]
            _LOGGER.debug("State updated to %s", self._state)
