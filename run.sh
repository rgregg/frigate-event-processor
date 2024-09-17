#!/bin/bash

docker build . -t frigate-event-processor
docker run --rm -v ./logs:/app/logs -v ./config.yaml:/app/config.yaml:ro frigate-event-processor