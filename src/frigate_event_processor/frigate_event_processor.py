import logging
import json
import threading
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from prettytable import PrettyTable
from .app_configuration import AppConfig, ZonesConfig
from .vision_processor import BaseVisionProcessor

logger = logging.getLogger(__name__)

class FrigateEventProcessor:
    """Main class for processing events from Frigate via MQTT"""

    def __init__(self, config: AppConfig, alert_publish_func):
        self.ongoing_events = dict()
        self.config = config
        self.configure_logging()
        self.cameras = {alert.camera: alert for alert in self.config.alerts}
        self.camera_notification_history = dict()
        self.label_notification_history = dict()
        self.event_processing_queue = dict()
        self.alert_publish_func = alert_publish_func
        self.ai_processor = BaseVisionProcessor.get_vision_engine(config.ai)

    def process_event(self, event):
        """ Main loop for processing events """
        event_type = event.get('type')
        before = event.get('before')
        after = event.get('after')

        if event_type == "new" or event_type == "update":
            self.process_event_data(after, event_type.upper())
        elif event_type == "end":
            self.process_end_event(before)

    def clear_pending_notifications(self):
        """ Cancel any pending timers queued """
        for _index, (_key, value) in enumerate(self.event_processing_queue.items()):
            value.cancel()
        self.event_processing_queue.clear()
        
    def process_event_data(self, data, tag):
        """ Indicates a new event has started """
        event = EventData(data)
        logger.info("%s: %s, camera=%s, label=%s, score=%s", tag, event.id, event.camera, event.label, event.score)

        # if we need to delay processing this event, queue the event
        if self.should_queue_event(event):
            self.queue_event_processing(event)
        else:
            previous = self.ongoing_events.get(event.id)
            self.process_event_for_alert(event, previous)

    def should_queue_event(self, event):
        """ Check to see if an event needs to be queued bsased on the start_time of the event """
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

    def queue_event_processing(self, event):
        """ Handles queuing an event for the required duration of time and/or adding an event to an existing queue """

        elapsed_time = datetime.now() - datetime.fromtimestamp(event.start_time)
        remaining_time = self.config.alert_rules.minimum_duration_seconds - elapsed_time.total_seconds()
        remaining_time = max(remaining_time, 0)

        logger.info("Queuing event %s for remaining minimum duration: %s", event.id, remaining_time)
        existing_queue = self.event_processing_queue.get(event.id)
        if existing_queue is None:
            existing_queue = EventProcessingQueue(event)
            self.event_processing_queue[event.id] = existing_queue
            
            existing_queue.timer = threading.Timer(remaining_time, self.process_event_queue, args=[existing_queue])
            existing_queue.timer.start()
        else:
            existing_queue.add_to_queue(event)

    def process_event_queue(self, event_queue):
        """
        Loops over the events stored into the event's queue and processes them in order to make sure
        we perform all the necessary notifications
        """

        del self.event_processing_queue[event_queue.id]
        previous = None
        for event in event_queue.queue:
            self.process_event_for_alert(event, previous)
            previous = event

    def process_event_for_alert(self, event, previous):
        """
        Evalautes an event to determine if it should be elevated to an alert
        """
        logger.info("Event %s: Processing new alert", event.id)
        self.ongoing_events[event.id] = event
        if self.evaluate_alert(previous, event):
            self.publish_event_to_mqtt(event)
    
    def publish_event_to_mqtt(self, event):
        """
        Publish an alert to the MQTT alerting topic
        """
        alert = self.generate_notification(event)
        self.camera_notification_history[event.camera] = alert
        self.label_notification_history[self.camera_and_label_key(event)] = alert

        alert_payload = json.dumps(alert.to_dict())
        logger.info("ALERT: %s", alert_payload)
        self.alert_publish_func(self.config.mqtt.alert_topic + "/alert", alert_payload)

        if self.config.event_tracking.enabled:
            self.publish_event_tracking(alert)

    def publish_event_tracking(self, alert):
        """ Publish the event to the event tracking MQTT topic """
        camera = alert.camera
        state_topic = f"{self.config.event_tracking.mqtt_topic}/{camera}"
        payload = json.dumps({
            "event_id": alert.event_id,
            "image_url": f"{self.config.event_tracking.home_assistant_url}/api/frigate/notifications/{alert.event_id}/snapshot.jpg",
            "message": alert.message
        })

        self.alert_publish_func(state_topic, payload)

    def generate_alert_for_event_id(self, event_id):
        """ Generate the alert content based on an event ID. Used for manually triggering alerts. """
        logger.info("Manually processing %s for alert", event_id)
        event = self.ongoing_events.get(event_id)
        if event is None:
            logger.warning("Event %s no longer available. Nothing generated.", event_id)
            return
        self.publish_event_to_mqtt(event)

    def get_ongoing_event(self, event_id):
        """ Get the ongoing event by ID """
        return self.ongoing_events.get(event_id)

    def log_info_event_id(self, event_id):
        """ Write information about a particular event to the log """
        event = self.ongoing_events.get(event_id)
        if event is None:
            logger.warning("Event %s no longer available.", event_id)
            return
        logger.info("Event %s: %s", event_id, event)
    
    def process_end_event(self, data):
        """ Indicates that the event has ended and the object
            is no longer detected in the video """
        event_id = data.get('id')
        logger.info("END: Event %s ended", event_id)

        existing_queue = self.event_processing_queue.get(event_id)
        if existing_queue:
            existing_queue.timer.cancel()
            del self.event_processing_queue[existing_queue.id]
            logger.info("Canceled processing %s since it ended before the min_duration", event_id)

        try:
            del self.ongoing_events[id]
        except KeyError:
            pass

    def evaluate_alert(self, before, after):
        """
        Compare events to see if we should create a new notification for this event
        """
        # check to see if this is a significant change from the previous event
        is_significant = True
        reason = ""
        if before is not None:
            if before.label != after.label:
                reason = "label"
            elif before.sub_label != after.sub_label:
                reason = "sub_label"
            elif before.current_zones != after.current_zones:
                reason = "current_zones"
            elif before.entered_zones != after.entered_zones:
                reason = "entered_zones"
            elif before.has_clip != after.has_clip and bool(after.has_clip):
                reason = "has_clip"
            elif before.has_snapshot != after.has_snapshot and bool(after.has_snapshot):
                reason = "has_snapshot"
            else:
                reason = "end of statements"
                is_significant = False
        else:
            reason = "new event - before was none"

        if not is_significant:
            logger.info("Event %s: not significant change.", before.id)
            return False

        logger.info("Event %s: was significant due to %s", after.id, reason)
        
        # check for max_duration
        if self.config.alert_rules.maximum_duration_seconds > 0:
            event_too_old = datetime.fromtimestamp(after.start_time) + timedelta(seconds=self.config.alert_rules.maximum_duration_seconds) < datetime.now()
            if event_too_old:
                logger.info("Event %s: too long duration for alert.", after.id)
                return False

        # check to see if this event meets the configuration criteria for this camera
        alert_config = self.config_for_camera(after.camera)
        if alert_config is None:
            logger.info("Event %s: no configuration for camera %s", after.id, after.camera)
            return True
        
        # is the alert enabled or disabled
        if not alert_config.enabled:
            logger.info("Event %s: configuration disabled for camera %s", after.id, after.camera)
            return False

        # is the alert for an expected object type (label)
        if not after.label in alert_config.labels:
            logger.info("Event %s: configuration missing for camera %s and label %s", after.id, after.camera, after.label)
            return False
        
        # is the event including a required zone?
        required_zones = alert_config.zones.require_zones
        if not ZonesConfig.check_zone_match(required_zones, after.current_zones, after.label, True):
            logger.info("Event %s: not in a required zone (camera=%s, label=%s, current_zones=%s)", after.id, after.camera, after.label, after.current_zones)
            return False
        
        # is the event in an ignored zone?
        ignored_zones = alert_config.zones.ignore_zones
        if ZonesConfig.check_zone_match(ignored_zones, after.current_zones, after.label, False):
            logger.info("Event %s: in ignored zone (camera=%s, label=%s, current_zones=%s)", after.id, after.camera, after.label, after.current_zones)
            return False
        
        # does the event have required parameters
        if self.config.alert_rules.require_snapshot and not after.has_snapshot:
            logger.info("Event %s: no snapshot", after.id)
            return False
        if self.config.alert_rules.require_video and not after.has_video:
            logger.info("Event %s: no video clip", after.id)
            return False
        
        # check to see if we're still in the event cooldown for the camera
        if not before and not self.is_event_past_cooldown(after):
            logger.info("Event %s: was still in cooldown time", after.id)
            return False
                
        return True
    
    
    def is_event_past_cooldown(self, event):
        """ Check to see if this event meets the required cooldown time in the configuration """
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
    
    def generate_location_string(self, event):
        """ Generate the location string for this event based on the camera name and current zones """

        camera = event.camera.replace("_", " ").title()
        if event.current_zones is not None and len(event.current_zones) > 0:
            zones = ", ".join(event.current_zones).replace("_", " ").title()
            return f"{camera} [{zones}]"
        else:
            return camera

    
    def generate_notification(self, event):
        """ Returns a JSON string representing the alert notification for this event """
        logger.debug("Event %s: Generating notification for event", event.id)

        detection = self.generate_detection_string(event)
        location = self.generate_location_string(event)
        notification = Notification(event)

        if getattr(self.ai_processor, 'enabled', False):
            logger.debug("Event %s: Processing with AI model", event.id)
            notification.message = self.ai_processor.process_event(detection, location, self.get_snapshot_url(event), event)
        else:
            logger.debug("Event %s: AI Model is disabled", event.id)

        if notification.message is None:
            logger.debug("Event %s: Generating default message", event.id)
            notification.message = f"{detection} was detected at {location}"
        
        notification.image = self.get_thumbnail_url(event)
        notification.video = self.get_video_url(event)

        return notification
    
    def get_snapshot_url(self, event):
        """ Get the snapshot URL for this event """
        return self.config.frigate.api_base_url + f"/events/{event.id}/snapshot.jpg"
    
    def get_thumbnail_url(self, event):
        """ Get the thumbnail URL for this event """
        return self.config.frigate.api_base_url + f"/events/{event.id}/thumbnail.jpg"
    
    def get_video_url(self, event):
        """ Get the video URL for this event """
        if event.has_clip:
            return self.config.frigate.api_base_url + f"/events/{event.id}/clip.mp4"
        return None
    
    def camera_and_label_key(self, event):
        """ Generate a unique key for this event based on the camera and label """
        return f"{event.camera}__{event.label}"

    def generate_detection_string(self, event):
        """ Generate the detection string for this event """
        output = event.label.replace("_", " ").title()  # "Person"
        if event.sub_label is not None:
            sub_labels = ', '.join([item['subLabel'].title() for item in event.sub_label])
            output = f"{output} ({sub_labels})"
        return output

    def config_for_camera(self, camera):
        """ Get the configuration for the camera """
        return self.cameras.get(camera)
        
    def configure_logging(self):
        """ Configure logging for the class """
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
            max_keep = self.config.logging.max_keep or 10
            handler = RotatingFileHandler(self.config.logging.path, maxBytes=5*1024*1024, backupCount=max_keep)
            handler.setLevel(level)
            formatter = logging.Formatter("%(asctime)-15s %(name)-8s %(levelname)s: %(message)s")
            handler.setFormatter(formatter)
            logging.getLogger().addHandler(handler)

    
    def print_ongoing_events(self):
        """ Print a table of ongoing events to the console """
        table = PrettyTable()
        table.field_names = ["ID", "Camera", "Zones", "Label", "SubLabel", "Score", "Duration"]

        for _index, (key, event) in enumerate(self.ongoing_events.items()):
            table.add_row([key, event.camera, ", ".join(event.current_zones), event.label, event.sub_label, "{:.2f}".format(event.score), event.duration])

        logger.info("\n%s", str(table))
                          

        
            


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