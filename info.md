[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)  [![made-with-python](https://img.shields.io/badge/Made%20with-Python-1f425f.svg)](https://www.python.org/) [![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.me/cyberjunkynl/)

# P2000 Sensor Component
This is a Custom Component for Home-Assistant (https://home-assistant.io) that tracks P2000 emergency events in The Netherlands.

## About
This component queries http://feeds.livep2000.nl at the configured interval and applies filters for range, type(s) and regio(s) set.

When events are found the P2000 sensor state gets set, which you can use to trigger automation, display sensor data,
and even plot location on the map.

## Usage
To use this component in your installation, add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry

sensor:
  - platform: p2000
    regios: 18
    disciplines: 1,2,3,4
    radius: 15000
    scan_interval: 20
    capcodes: 1403001, 1403003
  
  - platform: p2000
    name: Amsterdam
    regios: 13
    disciplines: 1,2,3,4
    radius: 10000
    scan_interval: 10
    latitude: 52.3680
    longitude: 4.9036
```

Configuration variables:

- **regios** (*Required*): You have to specify at least one, if you want more seperate them by commas.
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
- **disciplines** (*Optional*): Disciplines to display, separate them by commas. (default = 1,2,3,4)
 * 1 = Brandweer
 * 2 = Ambulance
 * 3 = Politie
 * 4 = KNRM
- **radius** (*Optional*): Only display on calls within this range in meters, it uses the lat/lon from your home-assistant.conf file as center or the optional values. (default = 5000)
- **scan_interval** (*Optional*): Check every x seconds. (default = 30)
- **name** (*Optional*): Name for sensor.
- **lat** (*Optional*): Latitude of center radius.
- **lon** (*Optional*): Longitude of center radius.
- **capcodes** (*Optional*): Capcode(s) you want to filter on. http://capcode.nl

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
        icon: 'mdi:ambulance'
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

## Donation
[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.me/cyberjunkynl/)
