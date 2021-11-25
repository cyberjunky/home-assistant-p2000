[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)  [![made-with-python](https://img.shields.io/badge/Made%20with-Python-1f425f.svg)](https://www.python.org/) [![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.me/cyberjunkynl/)

# P2000 Sensor Component

## NOTE: 
We now use a new RSS feed service provided by Erwin from http://p2000.brandweer-berkel-enschot.nl/ thanks!
Hence this version is in beta state.

# P2000 Sensor Component

This is a Custom Component for Home-Assistant (https://home-assistant.io) that tracks P2000 emergency events in The Netherlands.

## About
This component queries http://p2000.brandweer-berkel-enschot.nl/ at the configured interval and applies filters for range (if lat/lon is available), discipline(s) and regio(s) set.

When events are found the P2000 sensor state gets set, which you can use to trigger automation, display sensor data,
and even plot location on the map.

## Installation

### HACS - Recommended
- Have [HACS](https://hacs.xyz) installed, this will allow you to easily manage and track updates.
- Search for 'P2000'.
- Click Install below the found integration.
- Configure using the configuration instructions below.
- Restart Home-Assistant.

### Manual
- Copy directory `custom_components/p2000` to your `<config dir>/custom_components` directory.
- Configure with config below.
- Restart Home-Assistant.

## Usage
To use this component in your installation, add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entries

sensor:
  - platform: p2000
    scan_interval: 20
    capcodes: 1403001,1403003
    icon: mdi:fire-truck
    nolocation: true
    
  - platform: p2000
    name: Amsterdam
    regios: 13
    disciplines: Politiediensten
    radius: 10000
    scan_interval: 10
    latitude: 52.3680
    longitude: 4.9036
```

Configuration variables:

- **regios** (*Optional*): You can specify one, if you want more seperate them by commas, without it you trigger on all (is alot)
 * 0 = Gereserveerd
 * 1 = Groningen
 * 2 = Friesland
 * 3 = Drenthe
 * 4 = IJsselland
 * 5 = Twente
 * 6 = Noord en Oost Gelderland
 * 7 = Gelderland Midden
 * 8 = Gelderland Zuid
 * 9 = Utrecht
 * 10 = Noord Holland Noord
 * 11 = Zaanstreek-Waterland
 * 12 = Kennemerland
 * 13 = Amsterdam-Amstelland
 * 14 = Gooi en Vechtstreek
 * 15 = Haaglanden
 * 16 = Hollands Midden
 * 17 = Rotterdam Rijnmond
 * 18 = Zuid Holland Zuid
 * 19 = Zeeland
 * 20 = Midden- en West-Brabant
 * 21 = Brabant Noord
 * 22 = Brabant Zuid en Oost
 * 23 = Limburg Noord
 * 24 = Limburg Zuid
 * 25 = Flevoland
- **disciplines** (*Optional*): Disciplines to display, separate them by commas. (default = all of them)
 * Brandweerdiensten = Brandweer
 * Ambulancediensten = Ambulance
 * Politiediensten = Politie
 * Gereserveerd = Gereserveerd
 * [Possible more of them]
- **radius** (*Optional*): Only display on calls within this range in meters, it uses the lat/lon from your home-assistant.conf file as center or the optional latitude/longitude values.
- **scan_interval** (*Optional*): Check every x seconds. (default = 30)
- **name** (*Optional*): Name for sensor.
- **latitude** (*Optional*): Latitude of center radius.
- **longitude** (*Optional*): Longitude of center radius.
- **capcodes** (*Optional*): Capcode(s) you want to filter on. http://capcode.nl. You can specify one, if you want more seperate them by commas. (full 7 digit notation)
- **nolocation** (*Optional*): Set this to False if you only want events which contain location data (default = True)
- **contains** (*Optional*): Search for events which contains this word exactly how it is written, for example GRIP

NOTE:
Regarding capcodes;
Make sure you specify the correct matching regio(s) in your config and remove leading 0's ie. capcode 0100001 is received as 100001 

You can use a state trigger event to send push notifications like this:
```yaml
# Example automation.yaml entry

automation:
  - alias: 'P2000 Bericht'
    trigger:
      platform: state
      entity_id: sensor.p2000
    action:
      - service_template: notify.html5
        data_template:
          title: "P2000 Bericht"
          message: >
            {{ states.sensor.p2000.state + states.sensor.p2000.attributes.capcodes }}
          data:
            url: "https://www.google.com/maps/search/?api=1&query={{ states.sensor.p2000.attributes.latitude }},{{ states.sensor.p2000.attributes.longitude }}"
```

Above is for html5 notify, you can click the notify message to open google maps with the lat/lon location if available in the P2000 message.

## Screenshots

![alt text](https://github.com/cyberjunky/home-assistant-p2000/blob/master/screenshots/p2000sensor.png?raw=true "Screenshot Sensor")
![alt text](https://github.com/cyberjunky/home-assistant-p2000/blob/master/screenshots/p2000map.png?raw=true "Screenshot Map")
![alt text](https://github.com/cyberjunky/home-assistant-p2000/blob/master/screenshots/p2000multi.png?raw=true "Screenshot Multi")

Lovelace card example:

```yaml
cards:
      - entity: sensor.p2000
        name: P2000 Dordrecht
        type: sensor
      - entity: sensor.amsterdam
        icon: 'mdi:fire-truck'
        name: P2000 Amsterdam
        type: sensor
      - default_zoom: 7
        entities:
          - entity: sensor.p2000
          - entity: zone.home
          - entity: sensor.amsterdam
        title: P2000 Dordrecht & Amsterdam
        type: map
```

## Debugging
If you experience unexpected output, please create an issue.
Share your configuration and post some debug log info.
You can obtain this by adding this line to your config and restart homeassistant.


```
logger:
  default: info
  logs:
      custom_components.p2000: debug
```

## Donation
[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.me/cyberjunkynl/)
