#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import os
import socket
import ssl
import sys
import time
from queue import Queue

import paho.mqtt.client as mqtt

SERVER_ADDRESS = ('localhost', 2598)

# Logging Configuration
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

handler = logging.FileHandler('n2kparserlite.log')
handler.setLevel(logging.ERROR)

formatter = logging.Formatter('%(asctime)s-%(name)s-%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# AsyncIO Event Loop
event_loop = asyncio.get_event_loop()


CONFIG = dict()
DEVICE_NAME = ''
DEVICE_ID = ''
INFLUX_SOCKET = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

PAYLOAD_QUEUE = Queue(maxsize=50)


def on_connect(mqttc, obj, flags, rc):
    """MQTT Callback Function upon connecting to MQTT Broker"""
    if rc == 0:
        logger.debug("MQTT CONNECT rc: " + str(rc))
        logger.info("Succesfully Connected to MQTT Broker")


def on_publish(mqttc, obj, mid):
    """MQTT Callback Function upon publishing to MQTT Broker"""
    logger.debug("MQTT PUBLISH: mid: " + str(mid))


def on_disconnect(mqttc, obj, rc):
    """MQTT Callback Fucntion upon diconnecting from Broker"""
    if rc == 0:
        logger.debug("MQTT DISCONNECTED: rc: " + str(rc))
        logger.debug("Disconnected Successfully from MQTT Broker")

def setup_mqtt_client(mqtt_conf, mqtt_client):
    """Configure MQTT Client based on Configuration"""

    if mqtt_conf['TLS']['enable']:
        logger.info("TLS Setup for Broker")
        logger.info("checking TLS_Version")
        tls = mqtt_conf['TLS']['tls_version']
        if tls == 'tlsv1.2':
             tlsVersion = ssl.PROTOCOL_TLSv1_2
        elif tls == "tlsv1.1":
            tlsVersion = ssl.PROTOCOL_TLSv1_1
        elif tls == "tlsv1":
            tlsVersion = ssl.PROTOCOL_TLSv1
        else:
            logger.info("Unknown TLS version - ignoring")
            tlsVersion = None
        if not mqtt_conf['TLS']['insecure']:

            logger.info("Searching for Certificates in certdir")
            CERTS_DIR = mqtt_conf['TLS']['certs']['certdir']
            if os.path.isdir(CERTS_DIR):
                logger.info("certdir exists")
                CA_CERT_FILE = os.path.join(CERTS_DIR, mqtt_conf['TLS']['certs']['cafile'])
                CERT_FILE = os.path.join(CERTS_DIR, mqtt_conf['TLS']['certs']['certfile'])
                KEY_FILE = os.path.join(CERTS_DIR, mqtt_conf['TLS']['certs']['keyfile'])

                mqtt_client.tls_set(ca_certs=CA_CERT_FILE, certfile=CERT_FILE, keyfile=KEY_FILE, cert_reqs=ssl.CERT_REQUIRED, tls_version=tlsVersion)
            else:
                logger.error("certdir does not exist.. check path")
                sys.exit()
        else:
            mqtt_client.tls_set(ca_certs=None, certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=tlsVersion)
            mqtt_client.tls_insecure_set(True)
    
    if mqtt_conf['username'] and mqtt_conf['password']:
        logger.info("setting username and password for Broker")
        mqtt_client.username_pw_set(mqtt_conf['username'], mqtt_conf['password'])
    
    return mqtt_client


async def send_data(mqtt_client):
    global PAYLOAD_QUEUE
    global CONFIG
    global DEVICE_ID, DEVICE_NAME
    global INFLUX_SOCKET

    while not PAYLOAD_QUEUE.empty():
        for topic in CONFIG['nmea2k']['topics']:
            data =  ''.join(list(PAYLOAD_QUEUE.queue))
            PAYLOAD_QUEUE.queue.clear()
            topic_to_publish = DEVICE_NAME + '/' + DEVICE_ID + '/' + topic
            logger.debug(f'SEND-DATA: Payload Size: {len(data)}')
            mqtt_client.publish(topic_to_publish, data, qos=1)
            INFLUX_SOCKET.sendto(data.encode('utf-8'), (CONFIG['influx']['host'], CONFIG['nmea2k']['udp_port']))

async def nmea2k_stream_client(address, nmea2k_conf, mqttc):
    """Stream Client for reading incoming NMEA2000 Data"""
    global PAYLOAD_QUEUE
    PGNS = list(map(int, nmea2k_conf['pgnConfigs'].keys()))
    logger.debug('STREAM-CLIENT: Connecting To {} Port {}'.format(*address))
    reader, _ = await asyncio.open_connection(*address)

    logger.info('STREAM-CLIENT: Reading from N2KD Stream Server')
    mqttc.loop_start()
    while True:
        try:
            data = await reader.readuntil(separator=b'\n')
            if data:
                raw_data = data.decode().split('\n')[0]
                nmea2k_data = json.loads(raw_data)
                del nmea2k_data['prio']
                del nmea2k_data['dst']
            
                if nmea2k_data['pgn'] in PGNS:
                    logger.debug('STREAM-CLIENT:[PGN:{}] Description: {}'.format(nmea2k_data['pgn'], nmea2k_data['description']))
                    # logger.debug(nmea2k_data)
                    if 'fromSource' in list(nmea2k_conf['pgnConfigs'][str(nmea2k_data['pgn'])].keys()):
                        logger.info('STREAM-CLIENT:[PGN:{}] PGN Source Filter for {} ,SOURCE: {}'.format(
                            nmea2k_data['pgn'],
                            nmea2k_data['description'],
                            nmea2k_data['src'],
                        ))
                        if nmea2k_data['src'] != nmea2k_conf['pgnConfigs'][str(nmea2k_data['pgn'])]['fromSource']:
                            logger.info('STREAM-CLIENT:[PGN:{}] Skipping data: {} With SRC: {}'.format(
                                nmea2k_data['pgn'],
                                nmea2k_data['description'],
                                nmea2k_data['src'],
                            ))
                            continue
                            # go to next incoming data
                    
                    # Create a set of all available fields from the incoming frame
                    incoming_fields = set(nmea2k_data['fields'].keys())
                    fields_from_conf = set(nmea2k_conf['pgnConfigs'][str(nmea2k_data['pgn'])]['fieldLabels'])
                    logger.debug(f'STREAM-CLIENT: Fields To Log: {fields_from_conf.intersection(incoming_fields)}')
                    try:
                        for selected_field in fields_from_conf.intersection(incoming_fields):
                            if isinstance(nmea2k_data['fields'][selected_field], str):
                                lineproto_payload = '{},src=nmea2k,pgnSrc={} {}="{}" {}\n'.format(
                                    nmea2k_data['description'].replace(" ", "").lower(),
                                    nmea2k_data['src'],
                                    selected_field.replace(" ", "").lower(),
                                    nmea2k_data['fields'][selected_field],
                                    time.time_ns(),
                                )
                            else:
                                lineproto_payload = '{},src=nmea2k,pgnSrc={} {}={} {}\n'.format(
                                    nmea2k_data['description'].replace(" ", "").lower(),
                                    nmea2k_data['src'],
                                    selected_field.replace(" ", "").lower(),
                                    nmea2k_data['fields'][selected_field],
                                    time.time_ns(),
                                )
                            if PAYLOAD_QUEUE.full():
                                logger.info('STREAM-CLIENT: Queue Full -> Publish Data')
                                hf_task = asyncio.create_task(send_data(mqttc))
                                await hf_task
                            else:
                                # logger.info('STREAM-CLIENT: Pushing data to Payload Queue')
                                PAYLOAD_QUEUE.put_nowait(lineproto_payload)
                    except Exception as e:
                        logger.error(e)
            else:
                log.error('STREAM-CLIENT: No Data')
                return
            time.sleep(0.1)
        except Exception as e:
            logger.error(e)
            logger.error('Error during Stream Reading')
            break
    
    mqttc.loop_stop()


def parse_args():
    """Parse Arguments for configuration file"""

    parser = argparse.ArgumentParser(description='CLI to store Actisense-NGT Gateway values to InfluxDB and publish via MQTT')
    parser.add_argument('--config', '-c', type=str, required=True, help='JSON configuraton file with path')
    return parser.parse_args()


def main():
    """Initialization"""
    args = parse_args()

    if not os.path.isfile(args.config):
        logger.error("configuration file not readable. Check path to configuration file")
        sys.exit()
    
    global CONFIG
    with open(args.config, 'r') as config_file:
        CONFIG = json.load(config_file)

    global DEVICE_NAME, DEVICE_ID
    DEVICE_NAME = CONFIG['device']['name']
    DEVICE_ID = CONFIG['device']['ID']
    MQTT_CONF = CONFIG['mqtt']
    NMEA2K_CONF = CONFIG['nmea2k']

    mqttc = mqtt.Client(client_id=f'{DEVICE_NAME}/{DEVICE_ID}-NMEA2K')
    mqttc = setup_mqtt_client(MQTT_CONF, mqttc)

    mqttc.on_connect = on_connect
    mqttc.on_publish = on_publish
    mqttc.on_disconnect = on_disconnect

    mqttc.connect(CONFIG['mqtt']['broker'], CONFIG['mqtt']['port'])

    logger.info('AsyncIO - Event Loop - Start reading from Stream Server')
    try:
        event_loop.run_until_complete(
            nmea2k_stream_client(
                SERVER_ADDRESS,
                NMEA2K_CONF,
                mqttc
            )
        )
    except KeyboardInterrupt:
        logger.exception('CTRL+C Pressed')
        pass
    finally:
        mqttc.disconnect()
        logger.info('closing event loop')
        PAYLOAD_QUEUE.queue.clear()
        event_loop.close()


if __name__ == "__main__":
    main()
