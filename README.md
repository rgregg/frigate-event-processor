# Frigate Event Processor

![Python Tests](https://github.com/rgregg/frigate-event-processor/actions/workflows/python-tests.yml/badge.svg)

Frigate Event Processor (FEP) works with [Frigate](https://frigate.video) to monitor camera events and
use rules to filter detections that are then provided to an alerting system via MQTT.

## Features

- Per-camera filtering by label, required/ignored zones, minimum/maximum duration, and media availability
- Camera/label/group cooldown timers to prevent duplicate alerts from overlapping views
- MQTT alerts ready for Home Assistant automations plus optional event tracking sensors
- Optional AI-generated descriptions using Google Gemini or local Ollama models
- Lightweight deployment with Docker or Python and automated CI for tests + Docker images

### Filtering criteria

- Camera
- Label
- Zone (required or ignored zones)
- Minimum event duration (filter out events that last less than X seconds)
- Maximum event duration (filter out events which started more than X seconds ago)
- Snapshot or Video
- Camera groups to avoid duplicate alerts when views overlap

You can also easily implement a cooldown feature for a camera, label, or a group of cameras so a
single person walking through overlapping views will only trigger one notification.

## Quick Start

1. Copy `config_example.yaml` to `config.yaml` and update the `mqtt` and `frigate` blocks.
2. Customize the `alerts`, `alert_rules`, and `groups` sections for your cameras.
3. Run FEP:

```bash
# Local Python
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=./src CONFIG_FILE=./config.yaml python -m frigate_event_processor.main

# Or Docker Compose (see below for full service definition)
docker compose up -d event-processor
```

4. Add the Home Assistant automation (below) to receive notifications.

## Configuration Overview

- **`mqtt`**: connection info, incoming `listen_topic`, and outgoing `alert_topic`.
- **`frigate`**: host + protocol for snapshot/clip URLs.
- **`alerts`**: per-camera rules (labels, enabled flag, zone require/ignore lists).
- **`alert_rules`**: global min/max durations, `snapshot`/`video` requirements, and cooldown timers (`camera`, `label`, `group`).
- **`groups`**: cameras that overlap and should share a cooldown.
- **`event_tracking`**: optional MQTT sensors/Home Assistant discovery config.
- **`ai`**: enable Gemini/Ollama processors for descriptive push notifications.
- **`logging`**: log level, file path, and MQTT debug options.

## Example Configuration File

```yaml
mqtt:
  host: mqtt-server.lan
  port: 1883
  listen_topic: frigate/events
  alert_topic: alerts/camera_system

frigate:
  host: frigate-server.lan
  port: 5000
  ssl: false

alerts:
  - camera: yard
    enabled: true
    labels:
      - person
  - camera: front_door
    labels:
      - car
      - person
      - package
    zones:
      ignore:
        - zone: street
          labels: ["car"]  # ignore the label car in the parked_cars zone

  - camera: backyard
    labels:
      - person
    require:
      - zone: steps
        labels: ["*"]

alert_rules:
  # Minimum duration of time an event is active before a notification is fired, 0 to disable
  # Note this will delay processing of all alert notifications for at least this duration of
  # time to make sure the event doesn't end first. Recommend to keep this to a low value to
  # ensure timely delivery of alerts
  min_event_duration: 1.1s
  
  # maximum time since the event was created that will still generate an alert (this can be used
  # to prevent alerts for parked cars and other items that are detected for a long time)
  max_event_duration: 1m

  # Require that a snapshot is avaialble before a notificaiton is fired
  snapshot: false

  # Require that a video is avaialble before a notification is fired
  video: false

  cooldown:
    # Amount of time that must elapse before a notification is fired again for the same camera
    camera: 0s  # 30s or 5m or 1h

    # Amount of time that must elapse before a notification is fired again for the same label on a camera
    label: 1m

# Define camera groups where cameras overlap and share a cooldown timer
groups:
  porch:
    - front_door
    - front_steps
  yard:
    - yard
    - backyard

object_tracking:
  # enable tracking location of labels on video frames to identify stationary objects and supress alerts
  enabled: true

logging:
  level: INFO
  path: "./logs/frigate-processor.log"
  max-keep: 10
```

## Testing & Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install pytest
python -m pytest
```

GitHub Actions automatically runs the pytest suite on every push or pull request to `main` and `dev`.
A second workflow builds/pushes the Docker image after the tests succeed.

## Running with Docker Compose

The easiest way to run FEP is to add it to your Docker Compose environment where you are already
running Frigate and MQTT:

```yaml
services:
  frigate:
    # your frigate configuration here
  event-processor:
    container_name: frigate-event-processor
    image: rgregg/frigate-event-processor:main
    restart: unless-stopped
    volumes:
      - ./fep/logs:/app/logs
      - ./fep/config.yaml:/app/config.yaml:ro
    depends_on:
      - frigate
```

FEP is light weight and only requires access to your MQTT server - you can run it on any box that
has access to MQTT.


## Home Assistant Notifications
You can use FEP with Home Assistant to push notifications to your mobile device using an automation
assoicated with the MQTT topic that FEP publishes on. Here is an example automation YAML:

```yaml
alias: Frigate - Deliver Processed Events
description: Send mobile notifications when Frigate detects something
triggers:
  - alias: When a Frigate event has been received
    topic: alerts/camera_system/alert
    variables:
      event: "{{ trigger.payload_json }}"
      camera: "{{ trigger.payload_json['camera'] }}"
      id: "{{ trigger.payload_json['id'] }}"
      message: "{{ trigger.payload_json['message'] }}"
    trigger: mqtt
conditions: []
actions:
  - alias: Send mobile notification
    choose:
      - conditions:
          - alias: If the event has a snapshot
            condition: template
            value_template: "{{ event.image != none }}"
        sequence:
          - alias: Send notification with an image
            data:
              title: Home Assistant
              message: "{{ message }}"
              data:
                url: /dashboard-cameras/{{ camera }}
                clickAction: /dashboard-cameras/{{ camera }}
                image: /api/frigate/notifications/{{ id }}/snapshot.jpg
                group: frigate-{{ camera }}
                tag: "{{ id }}"
            enabled: true
            action: notify.mobile_phone
        alias: Send notification with a picture
      - conditions: []
        sequence:
          - alias: Send notification without an image
            data:
              title: Home Assistant
              message: "{{ message }}"
              data:
                url: /dashboard-cameras/{{ camera }}
                clickAction: /dashboard-cameras/{{ camera }}
                group: frigate-{{ camera }}
                tag: "{{ id }}"
            enabled: true
            action: notify.mobile_phone
        alias: Send notification without a picture
mode: parallel
max: 10

```

## Contributing & Support

Issues and pull requests are welcome! Feel free to open a ticket for feature requests or bugs. If you
extend the configuration (new AI engines, MQTT integrations, etc.), please add or update tests so the
GitHub Actions suite stays green. For questions, start a GitHub Discussion or file an issue.
