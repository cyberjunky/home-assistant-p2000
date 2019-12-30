"""
Support for fetching P2000 emergency service events near your location in The Netherlands.

"""
import logging
import datetime
import requests
import voluptuous as vol
import feedparser
from geopy.distance import vincenty

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_NAME, STATE_UNKNOWN, ATTR_ATTRIBUTION, ATTR_LONGITUDE,
    ATTR_LATITUDE, CONF_LONGITUDE, CONF_LATITUDE, CONF_RADIUS
    )
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
import homeassistant.util as util

BASE_URL = 'https://feeds.livep2000.nl?r={}&d={}'
_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=10)

CONF_REGIOS = 'regios'
CONF_DISCIPLINES = 'disciplines'
CONF_ATTRIBUTION = 'Data provided by feeds.livep2000.nl'

DEFAULT_NAME = 'P2000'
ICON = 'mdi:ambulance'
DEFAULT_DISCIPLINES = '1,2,3,4'
DEFAULT_RADIUS_IN_MTR = 5000

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_REGIOS): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_DISCIPLINES, default=DEFAULT_DISCIPLINES): cv.string,
    vol.Optional(CONF_RADIUS, default=DEFAULT_RADIUS_IN_MTR): vol.Coerce(float),
    vol.Optional(CONF_LATITUDE): cv.latitude,
    vol.Optional(CONF_LONGITUDE): cv.longitude,
})

async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up the P2000 sensor."""

    name = config.get(CONF_NAME)
    regios = config.get(CONF_REGIOS)
    disciplines = config.get(CONF_DISCIPLINES)
    latitude = util.convert(config.get(CONF_LATITUDE, hass.config.latitude), float)
    longitude = util.convert(config.get(CONF_LONGITUDE, hass.config.longitude), float)
    radius_in_mtr = config[CONF_RADIUS]
    url = BASE_URL.format(regios, disciplines)

    data = P2000Data(hass, latitude, longitude, url, radius_in_mtr)
    try:
        await data.async_update()
    except ValueError as err:
        _LOGGER.error("Error while fetching data from the P2000 portal: %s", err)
        return

    async_add_devices([P2000Sensor(data, name)], True)


class P2000Data(object):
    """Handle P2000 object and limit updates."""

    def __init__(self, hass, latitude, longitude, url, radius_in_mtr):
        """Initialize the data object."""
        self._lat = latitude
        self._lon = longitude
        self._url = url
        self._maxdist = radius_in_mtr
        self._feed = None
        self._lastmsg_time = None
        self._restart = True
        self._data = None

    @staticmethod
    def _convert_time(time):
        return datetime.datetime.strptime(
            time.split(",")[1][:-6]," %d %b %Y %H:%M:%S"
        )

    @property
    def latest_data(self):
        """Return the latest data object."""
        if self._data:
            return self._data
        return None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        _LOGGER.debug("Fetch URL: %s", self._url)
        try:
            self._feed = feedparser.parse(self._url,
                etag=None if not self._feed
                else self._feed.get('etag'),
                modified=None if not self._feed
                else self._feed.get('modified'))
            _LOGGER.debug("Fetched data = %s", self._feed)

            if not self._feed:
                _LOGGER.debug("Failed to get data from feed")
            else:
                msgtext = ''
                if self._feed.bozo != 0:
                    _LOGGER.debug("Error parsing feed %s", self._url)
                elif len(self._feed.entries) > 0:
                    _LOGGER.debug("%s entries downloaded",
                        len(self._feed.entries),
                        self._url)

                    if self._restart:
                        pubdate = self._feed.entries[0]['published']
                        self._lastmsg_time = self._convert_time(pubdate)
                        self._restart = False
                        _LOGGER.info("Last datestamp read %s", self._lastmsg_time)
                        return

                    for item in reversed(self._feed.entries):
                        lat_event = 0.0
                        lon_event = 0.0
                        dist = 0

                        if 'published' in item:
                            pubdate = item.published
                            lastmsg_time = self._convert_time(pubdate)

                        if lastmsg_time < self._lastmsg_time:
                            continue

                        _LOGGER.debug("New emergency event found.")
                        self._lastmsg_time = lastmsg_time

                        if 'geo_lat' in item:
                            lat_event = float(item.geo_lat)
                        else:
                            continue

                        if 'geo_long' in item:
                            lon_event = float(item.geo_long)
                        else:
                            continue

                        if lat_event and lon_event:
                            p1 = (self._lat, self._lon)
                            p2 = (lat_event, lon_event)
                            dist = vincenty(p1, p2).meters

                            msgtext = item.title.replace("~", "")+'\n'+pubdate+'\n'
                            _LOGGER.debug("Calculated distance %d meters, max. range %d meters", dist, self._maxdist)
                        if dist > self._maxdist:
                            msgtext = ''
                            _LOGGER.debug("Outside range")
                            continue

                if msgtext != "":
                    event = {}
                    event['msgtext'] = msgtext
                    event['latitude'] = lat_event
                    event['longitude'] = lon_event
                    event['distance'] = int(round(dist))
                    event['msgtime'] = lastmsg_time
                    _LOGGER.debug("Text: %s, Time: %s, Lat: %s, Long: %s, Distance: %s",
                        event['msgtext'], event['msgtime'], event['latitude'], event['longitude'], event['distance'])
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
            attrs[ATTR_LONGITUDE] = data['longitude']
            attrs[ATTR_LATITUDE] = data['latitude']
            attrs['distance'] = data['distance']
            attrs['time'] = data['msgtime']
            attrs[ATTR_ATTRIBUTION] = CONF_ATTRIBUTION
        return attrs

    async def async_update(self):
        """Update current values."""
        await self._data.async_update()
        data = self._data.latest_data
        if data:
            self._state = data['msgtext']
            _LOGGER.debug("State updated to %s", self._state)

