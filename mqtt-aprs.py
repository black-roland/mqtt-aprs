#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-

__author__ = "Steve Miller"
__copyright__ = "Copyright (C) Steve Miller"

__credits__ = ["Mike Loebl - https://github.com/mloebl/mqtt-aprs"]
__license__ = "GPL"
__version__ = "2.0.0"
__maintainer__ = "Steve Miller"
__email__ = "smiller _at_ kc1awv _dot_ net"
__status__ = "Development"

# Script based on mqtt-owfs-temp written by Kyle Gordon and converted for use with APRS
# Source: https://github.com/kylegordon/mqtt-owfs-temp
# Additional Python 3 development and conversions of Mike Loebl's code by Steve Miller, KC1AWV
# Source: https://github.com/mloebl/mqtt-aprs
# APRS is a registered trademark Bob Bruninga, WB4APR

import configparser
import json
import logging
import os
import signal
import sys
import time

import aprslib
import paho.mqtt.client as paho
import setproctitle

# Read the config file
config = configparser.RawConfigParser()
config.read(os.environ.get("CONFIG_PATH", "/etc/mqtt-aprs/mqtt-aprs.cfg"))

# Use configparser to read the settings
DEBUG = config.getboolean("global", "debug")
MQTT_HOST = config.get("global", "mqtt_host")
MQTT_PORT = config.getint("global", "mqtt_port")
MQTT_TLS = config.getint("global", "mqtt_tls")
MQTT_SUBTOPIC = config.get("global", "mqtt_subtopic")
# Support both mqtt_root (new) and mqtt_prefix (legacy) for backward compatibility
try:
    MQTT_ROOT = config.get("global", "mqtt_root")
    MQTT_TOPIC = MQTT_ROOT + "/" + MQTT_SUBTOPIC
except configparser.NoOptionError:
    # Fall back to legacy mqtt_prefix if mqtt_root is not defined
    MQTT_PREFIX = config.get("global", "mqtt_prefix")
    MQTT_TOPIC = MQTT_PREFIX + "/" + MQTT_SUBTOPIC
MQTT_USERNAME = config.get("global", "mqtt_username")
MQTT_PASSWORD = config.get("global", "mqtt_password")
METRICUNITS = config.get("global", "metricunits")
MQTT_QOS = config.getint("global", "mqtt_qos", fallback=1)

APRS_CALLSIGN = config.get("global", "aprs_callsign")
APRS_PASSWORD = config.get("global", "aprs_password")
APRS_HOST = config.get("global", "aprs_host")
APRS_PORT = config.get("global", "aprs_port")
APRS_FILTER = config.get("global", "aprs_filter")

APRS_LATITUDE = config.get("global", "aprs_latitude")
APRS_LONGITUDE = config.get("global", "aprs_longitude")

APPNAME = MQTT_SUBTOPIC
PRESENCETOPIC = MQTT_TOPIC + "/state"
setproctitle.setproctitle("mqtt-aprs " + APPNAME)
client_id = APPNAME + "_%d" % os.getpid()

LOGFORMAT = "%(message)s"

mqttc = paho.Client(paho.CallbackAPIVersion.VERSION2)
aprs = None

is_shutting_down = False

if DEBUG:
    logging.basicConfig(level=logging.DEBUG, format=LOGFORMAT)
else:
    logging.basicConfig(level=logging.INFO, format=LOGFORMAT)

logging.info("Starting %s service", APPNAME)
if DEBUG:
    logging.info("Running in DEBUG mode")
else:
    logging.info("Running in INFO mode")


def celciusConv(fahrenheit):
    return (fahrenheit - 32) * (5 / 9)


def fahrenheitConv(celsius):
    return (celsius * (9 / 5)) + 32


# MQTT Callbacks


def on_publish(client, userdata, mid, reason_code, properties):
    logging.debug("Message published with ID: %d", mid)


def on_subscribe(client, userdata, mid, reason_code_list, properties):
    logging.debug("Subscription acknowledged for MID: %d", mid)


def on_unsubscribe(client, userdata, mid, reason_code, properties):
    logging.debug("Unsubscription acknowledged for MID: %d", mid)


def on_connect(client, userdata, connect_flags, reason_code, properties):
    logging.debug("Connection callback - Reason code: %d", reason_code)
    if reason_code == 0:
        logging.info("Successfully connected to MQTT broker at %s:%s", MQTT_HOST, MQTT_PORT)
        mqttc.publish(PRESENCETOPIC, "1", qos=0, retain=True)
        process_connection()
    elif reason_code == 1:
        logging.error("Connection refused - unacceptable protocol version")
        cleanup(1)
    elif reason_code == 2:
        logging.error("Connection refused - identifier rejected")
        cleanup(2)
    elif reason_code == 3:
        logging.warning("Connection refused - server unavailable, retrying in 30 seconds")
        time.sleep(30)
    elif reason_code == 4:
        logging.error("Connection refused - bad username or password")
        cleanup(4)
    elif reason_code == 5:
        logging.error("Connection refused - not authorized")
        cleanup(5)
    else:
        logging.error("Connection failed with unknown reason code: %d", reason_code)
        cleanup(reason_code)


def on_disconnect(client, userdata, reason_code, properties=None, rc=None):
    global is_shutting_down
    if reason_code == 0:
        logging.info("Cleanly disconnected from MQTT broker")
    elif not is_shutting_down:
        logging.warning("Unexpected disconnection from MQTT broker (reason code: %s)", str(reason_code))
        logging.info("Reconnecting in 5 seconds...")
        time.sleep(5)
    else:
        logging.info("Disconnected from MQTT broker during shutdown (reason code: %s)", str(reason_code))


def on_message(client, userdata, msg):
    logging.debug("MQTT message received on topic '%s' with QoS %d: %s",
                  msg.topic, msg.qos, msg.payload)
    process_message(msg)


def on_log(client, userdata, level, buf):
    logging.debug("MQTT client log: %s", buf)


def cleanup(signum=0, frame=None):
    global is_shutting_down
    is_shutting_down = True
    logging.info("Received signal %d, shutting down gracefully", signum)
    try:
        # Disconnect MQTT client
        logging.info("Disconnecting from MQTT broker")
        mqttc.publish(PRESENCETOPIC, "0", qos=0, retain=True)
        mqttc.disconnect()
        mqttc.loop_stop()
        # Close APRS connection if it exists
        if aprs is not None:
            logging.info("Closing APRS-IS connection")
            try:
                aprs.close()
            except Exception as e:
                logging.error("Error closing APRS connection: %s", e)
        # Small delay to ensure MQTT loop thread terminates
        time.sleep(0.5)
    except Exception as e:
        logging.error("Error during shutdown: %s", e)
    finally:
        logging.info("Shutdown complete")
        sys.exit(0 if signum in [2, 15] else signum)


def connect():
    logging.info("Connecting to MQTT broker at %s:%s", MQTT_HOST, MQTT_PORT)
    if MQTT_USERNAME:
        logging.debug("Setting MQTT username '%s'", MQTT_USERNAME)
        mqttc.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_TLS == 1:
        logging.info("Enabling TLS for MQTT connection")
        mqttc.tls_set()
    mqttc.will_set(PRESENCETOPIC, "0", qos=0, retain=True)
    result = mqttc.connect(MQTT_HOST, MQTT_PORT, 10)
    if result != 0:
        logging.warning("MQTT connection failed with error code %s, retrying in 10 seconds", result)
        time.sleep(10)
        connect()
    mqttc.on_connect = on_connect
    mqttc.on_disconnect = on_disconnect
    mqttc.on_publish = on_publish
    mqttc.on_subscribe = on_subscribe
    mqttc.on_unsubscribe = on_unsubscribe
    mqttc.on_message = on_message
    if DEBUG:
        mqttc.on_log = on_log
    mqttc.loop_start()


def process_connection():
    logging.debug("Processing connection")


def process_message(msg):
    logging.debug("Received: %s", msg.topic)


def find_in_sublists(lst, value):
    for sub_i, sublist in enumerate(lst):
        try:
            return (sub_i, sublist.index(value))
        except ValueError:
            pass
    raise ValueError("%s is not in lists" % value)


def callback(packet):
    logging.debug("APRS packet received: %s", packet)
    publish_aprstomqtt_nossid(json.dumps(packet))


def publish_aprstomqtt(inname, invalue):
    topic_path = MQTT_TOPIC + "/" + inname
    logging.debug("Publishing to MQTT topic '%s': %s", topic_path, invalue)
    mqttc.publish(topic_path, str(invalue).encode("utf-8").strip(), qos=MQTT_QOS)


def publish_aprstomqtt_ssid(inssid, inname, invalue):
    topic_path = MQTT_TOPIC + "/" + inssid + "/" + inname
    logging.debug("Publishing to MQTT topic '%s': %s", topic_path, invalue)
    mqttc.publish(topic_path, str(invalue).encode("utf-8").strip(), qos=MQTT_QOS)


def publish_aprstomqtt_nossid(invalue):
    topic_path = MQTT_TOPIC
    logging.debug("Publishing to MQTT topic '%s': %s", topic_path, invalue)
    mqttc.publish(topic_path, str(invalue).encode("utf-8").strip(), qos=MQTT_QOS)


def get_distance(inlat, inlon):
    if APRS_LATITUDE and APRS_LONGITUDE:
        R = 6373.0
        from math import atan2, cos, radians, sin, sqrt

        lat1 = radians(float(APRS_LATITUDE))
        lon1 = radians(float(APRS_LONGITUDE))
        lat2 = radians(float(inlat))
        lon2 = radians(float(inlon))
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        distance = R * c
        if METRICUNITS == "0":
            distance = distance * 0.621371
        return round(distance, 2)


def aprs_connect():
    logging.info("Connecting to APRS-IS server at %s:%s", APRS_HOST, APRS_PORT)
    if APRS_FILTER:
        logging.debug("Setting APRS filter: %s", APRS_FILTER)
        aprs.set_filter(APRS_FILTER)
    aprs.connect(blocking=True)
    logging.info("APRS-IS connection established, starting message consumer")
    aprs.consumer(callback)


signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)
try:
    aprs = aprslib.IS(
        APRS_CALLSIGN,
        passwd=APRS_PASSWORD,
        host=APRS_HOST,
        port=APRS_PORT,
        skip_login=False,
    )
    connect()
    aprs_connect()

except KeyboardInterrupt:
    logging.info("Interrupted by keypress")
    cleanup(0)
except aprslib.ConnectionDrop:
    logging.info("Connection to APRS server dropped, trying again in 30 seconds...")
    time.sleep(30)
    aprs_connect()
except aprslib.ConnectionError:
    logging.info("Connection to APRS server failed, trying again in 30 seconds...")
    time.sleep(30)
    aprs_connect()
except Exception as e:
    logging.error("Unexpected error: %s", e)
    cleanup(1)
