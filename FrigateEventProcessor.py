import logging
import json
import threading
from logging.handlers import RotatingFileHandler
from AppConfiguration import AppConfig, ZonesConfig
from datetime import datetime, timedelta
from prettytable import PrettyTable

logger = logging.getLogger(__name__)

class FrigateEventProcessor:
    def __init__(self, config: AppConfig, alert_publish_func):
        self.ongoing_events = dict()
        self.config = config
        self.configure_logging()
        self.cameras = {alert.camera: alert for alert in self.config.alerts}
        self.camera_notification_history = dict()
        self.label_notification_history = dict()
        self.event_process_timer = dict()
        self.alert_publish_func = alert_publish_func


    def process_event(self, event):
        type = event.get('type')
        before = event.get('before')
        after = event.get('after')

        if type == "new" or type == "update":
            self.process_event_data(after, type.upper())
        elif type == "end":
            self.process_end_event(before)

    """
    Cancel any pending timers queued
    """
    def clear_pending_notifications(self):
        for index, (key, value) in enumerate(self.event_process_timer.items()):
            value.cancel()
        self.event_process_timer.clear()
        
    """
    Indicates a new event has started
    """
    def process_event_data(self, data, tag):
        event = EventData(data)
        previous = self.ongoing_events.get(event.id)
        self.ongoing_events[event.id] = event
        logger.info(f"{tag}: {event.id}, camera={event.camera}, label={event.label}, score={event.score}")

        # check to see if we need to delay processing of this event
        if self.config.alert_rules.minimum_duration_seconds > 0:            
            event_start_time =  datetime.fromtimestamp(event.start_time)
            if event_start_time + timedelta(seconds=self.config.alert_rules.minimum_duration_seconds) > datetime.now():
                # queue this event for future processing
                event_id = event.id
                previous_timer = self.event_process_timer.get(event_id)
                if previous_timer is None:
                    logger.info(F"Queuing processing of event {event_id} for min duration {self.config.alert_rules.minimum_duration_seconds}")
                    timer = threading.Timer(self.config.alert_rules.minimum_duration_seconds, self.process_event_for_alert, args=[event, previous])
                    self.event_process_timer[event_id] = timer
                    timer.start()
                    return
                # TODO: if we already have a timer - we drop this event (which means we may not have the latest data for the alert...)

        self.process_event_for_alert(event, previous)

    def process_event_for_alert(self, event, previous):
        logger.info(F"Processing {event.id} for alert")
        if self.evaluate_alert(previous, event):
            self.publish_event_to_mqtt(event)

    def publish_event_to_mqtt(self, event):
        alert_payload = self.generate_notification_json(event)
        logger.info(f"ALERT: {alert_payload}")
        self.alert_publish_func(self.config.mqtt.alert_topic, alert_payload)

    def generate_alert_for_event_id(self, event_id):
        logger.info(F"Manually processing {event_id} for alert")
        event = self.ongoing_events.get(event_id)
        if event is None:
            logger.warning(f"Event {event_id} no longer available. Nothing generated.")
            return
        self.publish_event_to_mqtt(event)

    def log_info_event_id(self, event_id):
        event = self.ongoing_events.get(event_id)
        if event is None:
            logger.warning(f"Event {event_id} no longer available.")
            return
        logger.info(f"Event {event_id}: {event}")

    """
    Indicates that the event has ended and the object
    is no longer detected in the video
    """
    def process_end_event(self, data):
        id = data.get('id')
        
        previous_timer = self.event_process_timer.get(id)
        if previous_timer is not None:
            previous_timer.cancel()
            del self.event_process_timer[id]
            logger.info(F"Cancelling processing of {id} since it ended before the min_duration")

        del self.ongoing_events[id]
        logger.info(f"DEL: {id}")

    """
    Compare events to see if we should create
    a new notification for this event
    """
    def evaluate_alert(self, before, after):

        # check to see if this is a significant change from the previous event
        is_significant = True
        if before is not None:
            is_significant = (before.label != after.label or
                before.sub_label != after.sub_label or
                before.current_zones != after.current_zones or
                before.entered_zones != after.entered_zones or
                (before.has_clip != after.has_clip and after.has_clip == True) or
                (before.has_snapshot != after.has_snapshot and after.has_snapshot == True))

        if not is_significant:
            logger.info(f"Event update for {before.id} was not significant and was discarded.")
            return False
        
        # check for max_duration
        if self.config.alert_rules.maximum_duration_seconds > 0:
            event_too_old = datetime.fromtimestamp(after.start_time) + timedelta(seconds=self.config.alert_rules.maximum_duration_seconds) < datetime.now()
            if event_too_old:
                logger.info(f"Event {after.id} was too old and discarded.")
                return False


        # check to see if this event meets the configuration criteria for this camera
        alert_config = self.config_for_camera(after.camera)
        if alert_config is None:
            logger.info(f"No configuration for camera {after.camera}")
            return True
        
        # is the alert enabled or disabled
        if alert_config.enabled == False:
            logger.info(f"Event {after.id} (camera={after.camera}) was disabled in configuration")
            return False

        # is the alert for an expected object type (label)
        if not after.label in alert_config.labels:
            logger.info(f"Event {after.id} (camera={after.camera}, label={after.label}) was not included in configuration")
            return False
        
        # is the event including a required zone?
        required_zones = alert_config.zones.require_zones
        if not ZonesConfig.check_zone_match(required_zones, after.current_zones, after.label, True):
            logger.info(f"Event {after.id} (camera={after.camera}, label={after.label}, current_zones={after.current_zones}) was not in a required zone")
            return False
        
        # is the event in an ignored zone?
        ignored_zones = alert_config.zones.ignore_zones
        if ZonesConfig.check_zone_match(ignored_zones, after.current_zones, after.label, False):
            logger.info(f"Event {after.id} (camera={after.camera}, label={after.label}, current_zones={after.current_zones}) was in an ignored zone")
            return False
        
        # does the event have required parameters
        if self.config.alert_rules.require_snapshot and after.has_snapshot == False:
            logger.info(f"Event {after.id} (camera={after.camera}, label={after.label}) has no snapshot and was dropped")
            return False
        if self.config.alert_rules.require_video and after.has_video == False:
            logger.info(f"Event {after.id} (camera={after.camera}, label={after.label}) has no video clip and was dropped")
            return False
        
        # check to see if we're still in the event cooldown for the camera
        if not self.is_event_past_cooldown(after):
            logger.info(f"Event {after.id} (camera={after.camera}, label={after.label}) was still in cooldown and was skipped")
            return False
                
        return True
    
    def is_event_past_cooldown(self, event):
        cooldown = self.config.alert_rules.cooldown

        # If both camera and label cooldowns are 0, always return True
        if cooldown.camera_duration_seconds == 0 and cooldown.label_duration_seconds == 0:
            return True

        # Helper function to check cooldown expiration
        def is_past_cooldown(previous_notification, duration_seconds):
            if previous_notification is None or duration_seconds == 0:
                return True
            delta = timedelta(seconds=duration_seconds)
            return previous_notification.timestamp < (datetime.now() - delta)

        # Check camera cooldown
        camera_notification = self.camera_notification_history.get(event.camera)
        if not is_past_cooldown(camera_notification, cooldown.camera_duration_seconds):
            return False

        # Check label cooldown
        label_notification = self.label_notification_history.get(self.camera_and_label_key(event))
        if not is_past_cooldown(label_notification, cooldown.label_duration_seconds):
            return False

        return True

    def generate_location_string(event):
        
        if event.current_zones is not None and len(event.current_zones) > 0:
            zones = ", ".join(event.current_zones).title()
            return zones
        else:
            camera = event.camera.replace("_", " ").title()
            return camera

    def generate_notification_json(self, event):
        detection = self.generate_detection_string(event)
        location = self.generate_location_string(event)
        notification = Notification()
        notification.group = f"frigate-{event.camera.replace("_", "-")}"
        notification.tag = event.id
        notification.message = f"{detection} was detected at {location}"

        if event.has_snapshot:
            notification.image = self.config.frigate.api_base_url + f"/events/{event.id}/thumbnail.jpg"
        if event.has_clip:
            notification.video = self.config.frigate.api_base_url + f"/events/{event.id}/clip.mp4"

        self.camera_notification_history[event.camera] = notification
        self.label_notification_history[self.camera_and_label_key(event)] = notification
        return json.dumps(notification.to_dict())
    
    def camera_and_label_key(self, event):
        return f"{event.camera}__{event.label}"

    def generate_detection_string(self, event):
        output = event.label.replace("_", " ").title()  # "Person"
        if event.sub_label is not None:
            sub_labels = ', '.join([item['subLabel'].title() for item in event.sub_label])
            output = f"{output} ({sub_labels})"
        return output

    def config_for_camera(self, camera):
        return self.cameras.get(camera)
        
    def configure_logging(self):
        
        level = logging.INFO
        if self.config.logging.level.upper() == "DEBUG":
            level = logging.DEBUG
        if self.config.logging.level.upper() == "WARNING":
            level = logging.WARNING
        
        
        # enable logging
        logging.basicConfig(
            level=level,
            format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s",
        )

        if self.config.logging.path is not None:
            handler = RotatingFileHandler(self.config.logging.path, maxBytes=5*1024*1024, backupCount=self.config.logging.max_keep)
            handler.setLevel(level)
            formatter = logging.Formatter("%(asctime)-15s %(name)-8s %(levelname)s: %(message)s")
            handler.setFormatter(formatter)
            logging.getLogger().addHandler(handler)

    """
    Print a table of ongoing events to the console
    """
    def print_ongoing_events(self):
        table = PrettyTable()
        table.field_names = ["ID", "Camera", "Zones", "Label", "SubLabel", "Score", "Duration"]

        for index, (key, event) in enumerate(self.ongoing_events.items()):
            table.add_row([key, event.camera, ", ".join(event.current_zones), event.label, event.sub_label, "{:.2f}".format(event.score), event.duration])

        logger.info("\n"+str(table))

class Notification:
    def __init__(self):
        self.group = None
        self.tag = None
        self.message = None
        self.image = None
        self.video = None
        self.timestamp = datetime.now()
    # Method to convert the Notification object to a dictionary
    def to_dict(self):
        return {
            "group": self.group,
            "tag": self.tag,
            "message": self.message,
            "image": self.image,
            "video": self.video
        }


class EventData:
    def __init__(self, data):
        self.id = data.get('id')
        self.camera = data.get('camera')
        self.frame_time = data.get('frame_time')
        self.snapshot = data.get('snapshot')
        self.label = data.get('label')
        self.sub_label = data.get('sub_label', [])
        self.top_score = data.get('top_score')
        self.start_time = data.get('start_time')
        self.end_time = data.get('end_time')
        self.score = data.get('score', -1)
        self.box = data.get('box', [])
        self.area = data.get('area')
        self.ratio = data.get('ratio')
        self.region = data.get('region', [])
        self.stationary = data.get('stationary')
        self.motionless_count = data.get('motionless_count')
        self.position_changes = data.get('position_changes')
        self.current_zones = data.get('current_zones', [])
        self.entered_zones = data.get('entered_zones', [])
        self.has_clip = data.get('has_clip', False)
        self.has_snapshot = data.get('has_snapshot', False)
    
    @property
    def duration(self):
        started = datetime.fromtimestamp(self.start_time)
        delta = datetime.now() - started
        return str(delta)
    
    def to_dict(self):
        return {
            'id': self.id,
            'camera': self.camera,
            'frame_time': self.frame_time,
            'snapshot': self.snapshot,
            'label': self.label,
            'sub_label': self.sub_label,
            'top_score': self.top_score,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'score': self.score,
            'box': self.box,
            'area': self.area,
            'ratio': self.ratio,
            'region': self.region,
            'stationary': self.stationary,
            'motionless_count': self.motionless_count,
            'position_changes': self.position_changes,
            'current_zones': self.current_zones,
            'entered_zones': self.entered_zones,
            'has_clip': self.has_clip,
            'has_snapshot': self.has_snapshot
        }

    def __repr__(self):
        return f"Event({json.dumps(self.to_dict(), indent=2)})"
        
    