# Frigate Event Processor

Frigate Event Processor (FEP) works with [Frigate](https://frigate.video) to monitor camera events and
use rules to filter events which are then provided to an alerting system via MQTT.

FEP adds filtering capabiltiies so that every event that occurs doesn't generate a push notification
to your device. You can filter based on multiple criteria, including:

* Camera
* Label
* Sub-label
* Zone (required or ignored zones)
* Minimum event duration (filter out events that last less than X seconds)
* Maximum event duration (filter out events which started more than X seconds ago)
* Snapshot or Video

You can also easily implement a cooldown feature for a camera or label, to ensure that you won't
receive repeated alerts for the same detection within a small period of time.


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

object_tracking:
  # enable tracking location of labels on video frames to identify stationary objects and supress alerts
  enabled: true

logging:
  level: INFO
  path: "./logs/frigate-processor.log"
  max-keep: 10
```
