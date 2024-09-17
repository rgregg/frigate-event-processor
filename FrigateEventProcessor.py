import logging
import json
from logging.handlers import RotatingFileHandler
from AppConfiguration import AppConfig

logger = logging.getLogger(__name__)

class FrigateEventProcessor:
    def __init__(self, config: AppConfig):
        self.ongoing_events = dict()
        self.config = config
        self.cameras = {alert.camera: alert for alert in self.config.alerts}
        self.configure_logging()

    def process_event(self, event):

        type = event.get('type')
        before = event.get('before')
        after = event.get('after')

        if type == "new":
            self.process_new_event(after)
        elif type == "update":
            self.process_update_event(after)
        elif type == "end":
            self.process_end_event(before)

        
    """
    Indicates a new event has started
    """
    def process_new_event(self, data):
        event = EventData(data)
        self.ongoing_events[event.id] = event
        logger.info(f"NEW: {event.id}, camera={event.camera}, label={event.label}, score={event.score}")
        if self.evaluate_alert(None, event):
            alert = self.generate_notification_json(event)
            logger.info(f"ALERT: {json.dumps(alert)}")

    """
    Indicates information has been updated about an 
    event that we have already seen (probably...)
    """
    def process_update_event(self, data):
        event = EventData(data)
        logger.info(f"UPD: {event.id}, camera={event.camera}, label={event.label}, score={event.score}")

        previous = self.ongoing_events.get(event.id)
        self.ongoing_events[event.id] = event
        if self.evaluate_alert(previous, event):
            alert = self.generate_notification_json(event)
            logger.info(f"ALERT: {alert}")


    """
    Indicates that the event has ended and the object
    is no longer detected in the video
    """
    def process_end_event(self, data):
        id = data.get('id')
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
        
        # check to see if this event meets the configuration criteria for this camera
        alert_config = self.config_for_camera(after.camera)
        if alert_config is None:
            logger.info(f"No configuration for camera {after.camera}")
            return True
        
        # is the alert enabled or disabled
        if alert_config.enabled == False:
            logger.info(f"Alert for {after.id} (camera={after.camera}) was disabled in configuration")
            return False

        # is the alert for an expected object type (label)
        if not after.label in alert_config.objects:
            logger.info(f"Alert for {after.id} (camera={after.camera}, label={after.label}) was not included in configuration")
            return False
        
        # is the event including a required zone?
        required_zones = alert_config.zones.get('required', [])
        if len(required_zones) > 0 and len(set(required_zones) & set(after.current_zones)) == 0:
            logger.info(f"Alert for {after.id} (camera={after.camera}, label={after.label}, current_zones={after.current_zones}) was not in a required zone")
            return False
        
        # is the event in an ignored zone?
        ignored_zones = alert_config.zones.get('ignored', [])
        if len(ignored_zones) > 0 and len(set(ignored_zones) & set(after.current_zones)) == 0:
            logger.info(f"Alert for {after.id} (camera={after.camera}, label={after.label}, current_zones={after.current_zones}) was in an ignored zone")
            return False
        
        return True

    def generate_notification_json(self, event):
        camera = event.camera.replace("_", " ").title()
        detection = self.generate_detection_string(event)
        notification = Notification()
        notification.group = f"frigate-{event.camera.replace("_", "-")}"
        notification.tag = event.id
        notification.message = f"{detection} was detected on {camera}"

        if event.has_snapshot:
            notification.image = self.config.frigate.api_base_url + f"/events/{event.id}/thumbnail.jpg"
        if event.has_clip:
            notification.video = self.config.frigate.api_base_url + f"/events/{event.id}/clip.mp4"
        return json.dumps(notification.to_dict())

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

class Notification:
    def __init__(self):
        self.group = None
        self.tag = None
        self.message = None
        self.image = None
        self.video = None
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
    

        
    