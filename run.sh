#!/bin/bash

docker build . -t mqtt-logger
docker run --rm -v ./logs:/logs -e MQTT_BROKER=hestia.lan -e MQTT_PORT=1883 -e MQTT_TOPIC=frigate/events -e LOG_FILE=/logs/mqtt_logs.txt mqtt-logger
