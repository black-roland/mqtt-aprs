# mqtt-aprs

## This is a fork of Mike Loebl's code found at https://github.com/mloebl/mqtt-aprs

Connects to the specified APRS-IS server, and posts the APRS output to MQTT. It can parse parameters or dump the raw JSON from aprslib. It's currently for receive only from APRS-IS and sending to an MQTT server.

This script uses:

- `aprslib`, https://github.com/rossengeorgiev/aprs-python, to do the heavy APRS lifting
- `paho-mqtt`, https://www.eclipse.org/paho/index.php?page=clients/python/index.php for handling MQTT connect and pub / sub

### PREREQUISITES

- aprslib (pip3 install aprslib)
- paho-mqtt (pip3 install paho-mqtt)
- setproctitle (pip3 install setproctitle)

### USE

```bash
git clone https://github.com/black-roland/mqtt-aprs
cd mqtt-aprs
sudo cp doc/rotate.cfg /etc/mqtt-aprs/rotate.cfg
```

**Important:** Edit `/etc/mqtt-aprs/rotate.cfg` to suit your needs.

Then, simply run `python3 mqtt-aprs.py` and use an MQTT client to subscribe to the topics!

### SYSTEMD SERVICE

A systemd service file is provided to run `mqtt-aprs` as a service. To use it:

1. Copy the service file to the systemd directory:

   ```bash
   sudo cp doc/mqtt-aprs@.service /etc/systemd/system/mqtt-aprs@.service
   ```

2. Reload systemd to recognize the new service:

   ```bash
   sudo systemctl daemon-reload
   ```

3. Start the service with a specific configuration:

   ```bash
   sudo systemctl start mqtt-aprs@rotate
   ```

4. Enable the service to start on boot:
   ```bash
   sudo systemctl enable mqtt-aprs@rotate
   ```

### AVAILABLE TOPICS BY DEFAULT

The `aprs/rotate` topic (or any subtopic like `primary` or `fallback`) publishes a JSON object containing detailed APRS packet information. For example:

```json
{
  "topic": "aprs/rotate",
  "message": {
    "raw": "N0CALL-9>APRS,TCPIP*,qAC,T2TEST:!4903.50N/07201.75W#PHG5630/Test comment",
    "from": "N0CALL-9",
    "to": "APRS",
    "path": ["TCPIP*", "qAC", "T2TEST"],
    "via": "T2TEST",
    "messagecapable": false,
    "format": "uncompressed",
    "posambiguity": 0,
    "symbol": "#",
    "symbol_table": "/",
    "latitude": 49.0583,
    "longitude": -72.0292,
    "comment": "Test comment"
  },
  "time": 1741790793
}
```

### CONFIGURATION

The configuration file (`/etc/mqtt-aprs/rotate.cfg`) supports the following options:

- `DEBUG`: Enable or disable debug logging.
- `MQTT_HOST`: MQTT broker host.
- `MQTT_PORT`: MQTT broker port.
- `MQTT_TLS`: Enable or disable TLS.
- `MQTT_ROOT`: Base MQTT topic.
- `MQTT_QOS`: MQTT Quality of Service level (0, 1, or 2).
- `MQTT_SUBTOPIC`: Sub-topic for MQTT (e.g., `primary`, `fallback`, `rotate`).
- `MQTT_USERNAME`: MQTT username.
- `MQTT_PASSWORD`: MQTT password.
- `APRS_LATITUDE`: Latitude for distance calculation.
- `APRS_LONGITUDE`: Longitude for distance calculation.
- `APRS_CALLSIGN`: APRS callsign.
- `APRS_PASSWORD`: APRS password.
- `APRS_HOST`: APRS-IS server host.
- `APRS_PORT`: APRS-IS server port.
- `APRS_FILTER`: APRS filter.
- `METRICUNITS`: Use metric units for distance.

### WHY

Uh, why not? It's fun, and you could even do things like this:
![node-red worldmap](mqtt-aprs.png)

APRS is a registered trademark Bob Bruninga, WB4APR

Originally forked by Mike Loebl from original https://github.com/kylegordon/mqtt-owfs-temp, and customised for use with APRS

[mqtt-aprs](https://github.com/mloebl/mqtt-aprs) forked, modified and tested against Python 3 by Steve Miller
