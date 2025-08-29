#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-

__author__ = "Steve Miller"
__copyright__ = "Copyright (C) Steve Miller"

__credits__ = ["Mike Loebl - https://github.com/mloebl/mqtt-aprs"]
__license__ = "GPL"
__version__ = "0.0.1"
__maintainer__ = "Steve Miller"
__email__ = "smiller _at_ kc1awv _dot_ net"
__status__ = "Development"

# Script based on mqtt-owfs-temp written by Kyle Gordon and converted for use with APRS
# Source: https://github.com/kylegordon/mqtt-owfs-temp
# Additional Python 3 development and conversions of Mike Loebl's code by Steve Miller, KC1AWV
# Source: https://github.com/mloebl/mqtt-aprs
# APRS is a registered trademark Bob Bruninga, WB4APR

import os
import sys
import logging
import signal
import time
import json

import paho.mqtt.client as paho
import configparser

import setproctitle

import aprslib

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

mqttc = paho.Client(paho.CallbackAPIVersion.VERSION2)

LOGFORMAT = "%(asctime)-15s %(message)s"

if DEBUG:
    logging.basicConfig(level=logging.DEBUG, format=LOGFORMAT)
else:
    logging.basicConfig(level=logging.INFO, format=LOGFORMAT)

logging.info("Starting " + APPNAME)
logging.info("INFO MODE")
logging.debug("DEBUG MODE")


def celciusConv(fahrenheit):
    return (fahrenheit - 32) * (5 / 9)


def fahrenheitConv(celsius):
    return (celsius * (9 / 5)) + 32


# MQTT Callbacks


def on_publish(client, userdata, mid, reason_code, properties):
    logging.debug("MID" + str(mid) + " published.")


def on_subscribe(client, userdata, mid, reason_code_list, properties):
    logging.debug("Subscribe with mid " + str(mid) + " received.")


def on_unsubscribe(client, userdata, mid, reason_code, properties):
    logging.debug("Unsubscribe with mid " + str(mid) + " received.")


def on_connect(client, userdata, connect_flags, reason_code, properties):
    logging.debug("on_connect RC: " + str(reason_code))
    if reason_code == 0:
        logging.info("Connected to %s:%s", MQTT_HOST, MQTT_PORT)
        mqttc.publish(PRESENCETOPIC, "1", qos=0, retain=True)
        process_connection()
    elif reason_code == 1:
        logging.info("Connection refused - unacceptable protocol version")
        cleanup()
    elif reason_code == 2:
        logging.info("Connection refused - identifier rejected")
        cleanup()
    elif reason_code == 3:
        logging.info("Connection refused - server unavailable")
        logging.info("Retrying in 30 seconds")
        time.sleep(30)
    elif reason_code == 4:
        logging.info("Connection refused - bad username or password")
        cleanup()
    elif reason_code == 5:
        logging.info("Connection refused - not authorized")
        cleanup()
    else:
        logging.warning("Someting went wrong. RC:" + str(reason_code))
        cleanup()


def on_disconnect(client, userdata, reason_code, properties):
    if reason_code == 0:
        logging.info("Clean disconnect")
    else:
        logging.info("Unexpected disconnection! Reconnecting in 5 seconds")
        logging.debug("Result code: " + str(reason_code))
        time.sleep(5)


def on_message(client, userdata, msg):
    logging.debug(
        "Received: "
        + msg.payload
        + " received on topic "
        + msg.topic
        + " with QoS "
        + str(msg.qos)
    )
    process_message(msg)


def on_log(client, userdata, level, buf):
    logging.debug(buf)


def cleanup(signum, frame):
    logging.info("Disconnecting from broker")
    mqttc.publish(PRESENCETOPIC, "0", qos=0, retain=True)
    mqttc.disconnect()
    mqttc.loop_stop()
    logging.info("Exiting on signal %d", signum)
    sys.exit(signum)


def connect():
    logging.info("Connecting to %s:%s", MQTT_HOST, MQTT_PORT)
    if MQTT_USERNAME:
        logging.info("Found username %s", MQTT_USERNAME)
        mqttc.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_TLS == 1:
        logging.info("Using TLS for broker connection")
        mqttc.tls_set()
    mqttc.will_set(PRESENCETOPIC, "0", qos=0, retain=True)
    result = mqttc.connect(MQTT_HOST, MQTT_PORT, 10)
    if result != 0:
        logging.info("Connection failed with error code %s. Retrying", result)
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
    logging.debug("Raw packet: %s", packet)
    publish_aprstomqtt_nossid(json.dumps(packet))


def publish_aprstomqtt(inname, invalue):
    topic_path = MQTT_TOPIC + "/" + inname
    logging.debug("Publishing topic: %s with value %s" % (topic_path, invalue))
    mqttc.publish(topic_path, str(invalue).encode("utf-8").strip(), qos=MQTT_QOS)


def publish_aprstomqtt_ssid(inssid, inname, invalue):
    topic_path = MQTT_TOPIC + "/" + inssid + "/" + inname
    logging.debug("Publishing topic: %s with value %s" % (topic_path, invalue))
    mqttc.publish(topic_path, str(invalue).encode("utf-8").strip(), qos=MQTT_QOS)


def publish_aprstomqtt_nossid(invalue):
    topic_path = MQTT_TOPIC
    logging.debug("Publishing topic: %s with value %s" % (topic_path, invalue))
    mqttc.publish(topic_path, str(invalue).encode("utf-8").strip(), qos=MQTT_QOS)


def get_distance(inlat, inlon):
    if APRS_LATITUDE and APRS_LONGITUDE:
        R = 6373.0
        from math import sin, cos, sqrt, atan2, radians

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
    aprs.set_filter(APRS_FILTER)
    aprs.connect(blocking=True)
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
    sys.exit(0)
except aprslib.ConnectionDrop:
    logging.info("Connection to APRS server dropped, trying again in 30 seconds...")
    time.sleep(30)
    aprs_connect()
except aprslib.ConnectionError:
    logging.info("Connection to APRS server failed, trying again in 30 seconds...")
    time.sleep(30)
    aprs_connect
