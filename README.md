# nmea2kfluxlite

Python3 CLI similar to [n2kparser](https://github.com/iotfablab/n2kparser) with asynchronous reading of incoming NMEA2000 data from 
`n2kd` CLI by [canboat](https://github.com/canboat/canboat)

## Features

- Send data to InfluxDB on a hardware using UDP Socket directly
- Provide TLS settings for connecting to a Secure MQTT Broker
- Use a fixed length queue (see `PAYLOAD_QUEUE` in code) to store incoming NMEA2000 data in Line Protocol Format and send them to 
`DEVICE_NAME/DEVICE_ID/nmea2000` topic with `QoS=1`
- NMEA2000 PGNS can be configured via the `conf.json`

## Secure MQTT Configuration

Followig sample configuration for using a Secure MQTT Broker with Certificates. Use `insecure: true` to not use certificates.

```json
"mqtt": {
      "broker": "secure_broker",
      "port": 8883,
      "username": null,
      "password": null,
      "TLS": {
          "enable": true,
          "insecure": false,
          "tls_version": "tlsv1.2",
          "certs": {
            "certdir": "/etc/ssl/certs/mqtt",
            "cafile": "ca.crt",
            "certfile": "mqtt-client.crt",
            "keyfile": "mqtt-client.key"
          }
      }
    }
```

## systemd for `n2kd` Streaming Server

see the `nmea2kstreamer.service` and adapt the Serial Port for Actisense NGT-1 Gateway.

The stream socket is default at __2598__.


## PGN Configuration

Refer to [`n2kparser`](https://github.com/iotfablab/n2kparser) for how to adapt the `conf.json` to read different PGNs and filter
out specific source PGNs


## InfluxDB UDP Configuration

Sample configuration for `influxdb.conf`

```toml
[[udp]]
  enabled = true
  bind-address = ":8095"
  database = "IoTSink"
  precision = "n"
```
