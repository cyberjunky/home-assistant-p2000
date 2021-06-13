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
    CONF_ICON,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
import homeassistant.util as util
from homeassistant.util.location import distance

_LOGGER = logging.getLogger(__name__)

BASE_URL = "http://p2000.brandweer-berkel-enschot.nl/homeassistant/rss.asp"

DEFAULT_INTERVAL = datetime.timedelta(seconds=10)
DATA_UPDATED = "p2000_data_updated"

CONF_REGIOS = "regios"
CONF_DISCIPLINES = "disciplines"
CONF_CAPCODES = "capcodes"
CONF_ATTRIBUTION = "P2000 Livemonitor 2021 HomeAssistant"
CONF_NOLOCATION = "nolocation"
CONF_CONTAINS = "contains"

DEFAULT_NAME = "P2000"
DEFAULT_ICON = "mdi:ambulance"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_REGIOS): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_DISCIPLINES): cv.string,
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

    async_add_devices(
        [P2000Sensor(hass, data, config.get(CONF_NAME), config.get(CONF_ICON))], True
    )


class P2000Data:
    """Handle P2000 object and limit updates."""

    def __init__(self, hass, config):
        """Initialize the data object."""
        self._hass = hass
        self._lat = util.convert(config.get(CONF_LATITUDE, hass.config.latitude), float)
        self._lon = util.convert(
            config.get(CONF_LONGITUDE, hass.config.longitude), float
        )
        self._regios = config.get(CONF_REGIOS)
        self._url = BASE_URL
        self._nolocation = config.get(CONF_NOLOCATION)
        self._radius = config.get(CONF_RADIUS)
        self._capcodes = config.get(CONF_CAPCODES)
        self._contains = config.get(CONF_CONTAINS)
        self._disciplines = config.get(CONF_DISCIPLINES)
        self._capcodelist = None
        self._disciplinestable = {
            "Brandweerdiensten": "1",
            "Ambulancediensten": "2",
            "Politiediensten": "3",
            "Gereserveerd": "4",
        }
        self._feed = None

        self._restart = True
        self._event_time = None
        self._data = None

        if self._capcodes:
            self._capcodelist = self._capcodes.split(",")

        if self._regios:
            self._regioslist = self._regios.split(",")

        if self._disciplines:
            self._disciplineslist = self._disciplines.split(",")

    @property
    def latest_data(self):
        """Return the data object."""
        return self._data

    @staticmethod
    def _convert_time(time):
        try:
            return datetime.datetime.strptime(
                time.split(",")[1][:-6], " %d %b %Y %H:%M:%S"
            )
        except IndexError:
            return None

    async def async_update(self, dummy):
        """Update data."""

        self._feed = await self._hass.async_add_executor_job(
            feedparser.parse, self._url
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
                event_cap = ""
                event_time = self._convert_time(entry.published)
                if event_time < self._event_time:
                    continue
                self._event_time = event_time
                event_msg = entry.message
                _LOGGER.debug(
                    "New P2000 event found: %s, at %s", event_msg, entry.published
                )

                # Check regio
                if "regcode" in entry:
                    event_regio = entry.regcode.lstrip("0")
                    if self._regioslist:
                        _LOGGER.debug("Filtering on Regio(s) %s", self._regioslist)
                        regiofound = False
                        for regio in self._regioslist:
                            _LOGGER.debug(
                                "Searching for regio %s in %s",
                                regio,
                                event_regio,
                            )
                            if event_regio == regio:
                                _LOGGER.debug("Regio matched")
                                regiofound = True
                                break
                            _LOGGER.debug("Regio mismatch, discarding")
                            continue
                        if not regiofound:
                            continue

                if "dienst" in entry:
                    if self._disciplines:
                        try:
                            event_dienstcode = self._disciplinestable[entry.dienst]
                        except:
                            _LOGGER.debug("Unknown discipline %s", entry.dienst)
                        if self._disciplineslist:
                            _LOGGER.debug(
                                "Filtering on Disciplines(s) %s", self._disciplineslist
                            )
                            disciplinefound = False
                            for discipline in self._disciplineslist:
                                _LOGGER.debug(
                                    "Searching for discipline %s in %s",
                                    discipline,
                                    event_dienstcode,
                                )
                                if event_dienstcode == discipline:
                                    _LOGGER.debug("Discipline matched")
                                    disciplinefound = True
                                    break
                                _LOGGER.debug("Discipline mismatch, discarding")
                                continue
                            if not disciplinefound:
                                continue

                # Check radius or nolocation
                if "lat" in entry and entry.lat:
                    event_lat = float(entry.lat)
                    event_lon = float(entry.lon)
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

                # Check capcodes if defined
                if "code" in entry:
                    event_cap = entry.code.strip()
                    if self._capcodelist:
                        _LOGGER.debug("Filtering on Capcode(s) %s", self._capcodelist)
                        capfound = False
                        for capcode in self._capcodelist:
                            _LOGGER.debug(
                                "Searching for capcode %s in %s",
                                capcode.strip(),
                                event_cap,
                            )
                            if event_cap == capcode:
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
                    event["capcodetext"] = event_cap
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
            attrs["capcode"] = data["capcodetext"]
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
