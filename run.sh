#!/bin/bash

docker build . -t frigate-event-processor:dev-local
docker run --rm -v ./logs:/app/logs -v ./config.yaml:/app/config.yaml:ro frigate-event-processor:dev-local