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
        self.event_processing_queue = dict()
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
        for index, (key, value) in enumerate(self.event_processing_queue.items()):
            value.cancel()
        self.event_processing_queue.clear()
        
    """
    Indicates a new event has started
    """
    def process_event_data(self, data, tag):
        event = EventData(data)
        logger.info(f"{tag}: {event.id}, camera={event.camera}, label={event.label}, score={event.score}")

        # if we need to delay processing this event, queue the event
        if self.should_queue_event(event):
            self.queue_event_processing(event)
        else:
            previous = self.ongoing_events.get(event.id)
            self.process_event_for_alert(event, previous)

    """
    Check to see if an event needs to be queued bsased on the start_time of the event
    """
    def should_queue_event(self, event):
        # Check to see if there is a minimum event duration before we process events
        if self.config.alert_rules.minimum_duration_seconds > 0:            
            event_start_time =  datetime.fromtimestamp(event.start_time)
            elapsed_time = datetime.now() - event_start_time
            if elapsed_time.total_seconds() < self.config.alert_rules.minimum_duration_seconds:
                return True
            
        # If this event ID is already queued, don't break the queue
        if self.event_processing_queue.get(event.id) is not None:
            return True
        
        return False


    """
    Handles queuing an event for the required duration of time and/or adding an event to an existing queue
    """
    def queue_event_processing(self, event):
        elapsed_time = datetime.now() - datetime.fromtimestamp(event.start_time)
        remaining_time = self.config.alert_rules.minimum_duration_seconds - elapsed_time.total_seconds()
        if remaining_time < 0: remaining_time = 0

        logger.info(F"Queuing event {event.id} for remaining minimum duration: {remaining_time}")
        existing_queue = self.event_processing_queue.get(event.id)
        if existing_queue is None:
            existing_queue = EventProcessingQueue(event)
            self.event_processing_queue[event.id] = existing_queue
            
            existing_queue.timer = threading.Timer(remaining_time, self.process_event_queue, args=[existing_queue])
            existing_queue.timer.start()
        else:
            existing_queue.add_to_queue(event)

    """
    Loops over the events stored into the event's queue and processes them in order to make sure
    we perform all the necessary notifications
    """
    def process_event_queue(self, event_queue):
        del self.event_processing_queue[event_queue.id]
        previous = None
        for event in event_queue.queue:
            self.process_event_for_alert(event, previous)
            previous = event

    """
    Evalautes an event to determine if it should be elevated to an alert
    """
    def process_event_for_alert(self, event, previous):
        logger.info(F"Processing {event.id}...")
        self.ongoing_events[event.id] = event
        if self.evaluate_alert(previous, event):
            self.publish_event_to_mqtt(event)

    """
    Publish an alert to the MQTT alerting topic
    """
    def publish_event_to_mqtt(self, event):
        alert = self.generate_notification(event)
        self.camera_notification_history[event.camera] = alert
        self.label_notification_history[self.camera_and_label_key(event)] = alert

        alert_payload = json.dumps(alert.to_dict())
        logger.info(f"ALERT: {alert_payload}")
        self.alert_publish_func(self.config.mqtt.alert_topic + "/alert", alert_payload)

    """
    Generate the alert content based on an event ID. Used for manually triggering alerts.
    """
    def generate_alert_for_event_id(self, event_id):
        logger.info(F"Manually processing {event_id} for alert")
        event = self.ongoing_events.get(event_id)
        if event is None:
            logger.warning(f"Event {event_id} no longer available. Nothing generated.")
            return
        self.publish_event_to_mqtt(event)

    """
    Write information about a particular event to the log
    """
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
        logger.info(f"END: Event {id} ended")

        existing_queue = self.event_processing_queue.get(id)
        if existing_queue:
            existing_queue.timer.cancel()
            del self.event_processing_queue[existing_queue.id]
            logger.info(F"Canceled processing {id} since it ended before the min_duration")

        try:
            del self.ongoing_events[id]
        except KeyError:
            pass
        

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
    
    """
    Check to see if this event meets the required cooldown time in the configuration
    """
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

    """
    Generate the location string for this event based on the camera name and current zones
    """
    def generate_location_string(self, event):
        camera = event.camera.replace("_", " ").title()
        if event.current_zones is not None and len(event.current_zones) > 0:
            zones = ", ".join(event.current_zones).replace("_", " ").title()
            return f"{camera} [{zones}]"
        else:
            return camera

    """
    Returns a JSON string representing the alert notification for this event
    """
    def generate_notification(self, event):
        detection = self.generate_detection_string(event)
        location = self.generate_location_string(event)
        notification = Notification(event)
        notification.message = f"{detection} was detected at {location}"

        if event.has_snapshot:
            notification.image = self.config.frigate.api_base_url + f"/events/{event.id}/thumbnail.jpg"
        if event.has_clip:
            notification.video = self.config.frigate.api_base_url + f"/events/{event.id}/clip.mp4"

        return notification
    
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


class EventProcessingQueue:
    def __init__(self, event):
        self.id = event.id
        self.queue = [event]
        self.timer = None
    
    def add_to_queue(self, event):
        self.queue.append(event)




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
        
class Notification:
    def __init__(self, event: EventData):
        self.message = None
        self.image = None
        self.video = None
        
        self.group = f"frigate-{event.camera.replace("_", "-")}"
        self.event_id = event.id
        self.score = event.score
        self.label = event.label
        self.sub_label = event.sub_label
        self.camera =event.camera
        self.zones = event.current_zones
        self.timestamp = datetime.now()
    # Method to convert the Notification object to a dictionary
    def to_dict(self):
        return {
            "id": self.event_id,
            "group": self.group,
            "message": self.message,
            "score": self.score,
            "label": self.label,
            "sub_label": self.sub_label,
            "camera": self.camera,
            "zones": self.zones,
            "image": self.image,
            "video": self.video,
            "timestamp": str(self.timestamp)
            
        }