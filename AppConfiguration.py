import yaml
import logging
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
import re
from typing import List

# Define the classes to map the structure
logger = logging.getLogger(__name__)

class MqttConfig:
    def __init__(self):
        self.host = "localhost"
        self.port = 1883
        self.username = None
        self.password = None
        self.listen_topic = "#"
        self.alert_topic = "alerts/camera_system"

    def __repr__(self):
        return f"Mqtt(host={self.host}, username={self.username}, password={self.password}, listen_topic={self.listen_topic}, alert_topic={self.alert_topic})"

class FrigateConfig:
    def __init__(self):
        self.host = "localhost"
        self.port = 5000
        self.use_ssl = False

    @property
    def api_base_url(self):
        protocol = "https" if self.use_ssl else "http"
        return f"{protocol}://{self.host}:{self.port}/api"
    
    def __repr__(self):
        return f"Frigate(url={self.api_base_url})"

class AlertConfig:
    def __init__(self, camera):
        self.camera = camera
        self.labels = []
        self.enabled = True
        self.zones = ZonesConfig()

    def __repr__(self):
        return f"Alert(camera={self.camera}, objects={self.labels}, enabled={self.enabled}, zones={self.zones})"

class ZoneAndLabelsConfig:
    def __init__(self):
        self.zone = ""
        self.labels = []

    def __repr__(self):
        return f"ZoneAndLabel(zone={self.zone}, labels={self.labels})"


class ZonesConfig:
    def __init__(self):
        self.ignore_zones = []
        self.require_zones = []

    def __repr__(self):
        return f"Zones(ignored={self.ignore_zones}, required={self.require_zones})"
    
    @staticmethod 
    def check_zone_match(zone_configs: list[ZoneAndLabelsConfig], active_zones: list[str], label: str, default: bool) -> bool:
        if zone_configs is None or len(zone_configs) == 0:
            return default
        
        for config in zone_configs:
            # Check if the zone is in active_zones and the label is in the labels of the object
            if config.zone in active_zones:
                # if the label doesn't exist, the zone is enough - otherwise, if the rule has a * or matches the label
                if label is None or "*" in config.labels or label in config.labels:
                    return True
        return False

    @staticmethod
    def parse_zones(data):
        if data is None:
            return []
        
        config = []
        for item in data:
            zone = ZoneAndLabelsConfig()
            zone.zone = item.get('zone')
            zone.labels = item.get('labels')
            config.append(zone)

        return config



class CooldownConfig:
    def __init__(self):
        self.camera_duration_seconds = 0
        self.label_duration_seconds = 0

    def __repr__(self):
        return f"Cooldown(camera={self.camera_duration_seconds}, object={self.label_duration_seconds})"

class AlertRulesConfig:
    def __init__(self):
        self.minimum_duration_seconds = 0
        self.maximum_duration_seconds = 0
        self.require_snapshot = False
        self.require_video = False
        self.cooldown = CooldownConfig()

    def __repr__(self):
        return f"AlertRules(min_dur={self.minimum_duration_seconds}s, snapshots={self.require_snapshot}, video={self.require_video}, cooldown={self.cooldown})"

class ObjectTrackingConfig:
    def __init__(self):
        self.enabled = True

    def __repr__(self):
        return f"ObjectTracking(enabled={self.enabled})"
    
class LoggingConfig:
    def __init__(self):
        self.level = logging.INFO
        self.path = None
        self.rotate = False
        self.max_keep = 10

class AppConfig:
    def __init__(self):
        self.mqtt = MqttConfig()
        self.frigate = FrigateConfig()
        self.alerts = []
        self.alert_rules = AlertRulesConfig()
        self.object_tracking = ObjectTrackingConfig()
        self.logging = LoggingConfig()

    def apply_from_dict(self, data):
        # Parse mqtt
        self.load_mqtt_config(data)

        # Parse frigate
        self.load_frigate_config(data)

        # Parse alerts/cameras
        self.load_alerts_config(data)

        # Parse alert_rules
        self.load_rules_config(data)
        
        # Parse object tracking
        self.load_tracking_config(data)

        # Parse logger
        self.load_logging_config(data)

    def load_logging_config(self, data):
        logging = data.get('logging')
        if logging is not None:
            self.logging.level = logging.get('level')
            self.logging.path = logging.get('path')
            self.logging.rotate = logging.get('rotate')
            self.logging.max_keep = logging.get('max_keep')

    def load_tracking_config(self, data):
        tracking = data.get('object_tracking')
        if tracking is not None:
            self.object_tracking.enabled = tracking.get('enabled')
        else:
            self.object_tracking.enabled = True

    def load_rules_config(self, data):
        rules = data.get('alert_rules')
        if rules is not None:
            self.alert_rules.minimum_duration_seconds = self.parse_duration(rules.get('min_event_duration', "0s"))
            self.alert_rules.maximum_duration_seconds = self.parse_duration(rules.get('max_event_duration', "0s"))
            self.alert_rules.require_snapshot = rules.get('snapshot', False)
            self.alert_rules.require_video = rules.get('video', False)

            cooldown = rules.get('cooldown')
            if cooldown is not None:
                self.alert_rules.cooldown.camera_duration_seconds = self.parse_duration(cooldown.get('camera', "0s"))
                self.alert_rules.cooldown.label_duration_seconds = self.parse_duration(cooldown.get('label', "0s"))
        else:
            self.alert_rules.cooldown.camera_duration_seconds = 0
            self.alert_rules.cooldown.label_duration_seconds = 0

    def load_alerts_config(self, data):
        alerts = data.get('alerts')
        self.alerts.clear()
        for alert in alerts:
            new_alert = AlertConfig(alert.get('camera'))
            new_alert.enabled = alert.get('enabled') or True
            new_alert.labels = alert.get('labels') or []
            
            zones = alert.get('zones')
            if zones is not None:
                new_alert.zones.ignore_zones = ZonesConfig.parse_zones(zones.get('ignore'))
                new_alert.zones.require_zones = ZonesConfig.parse_zones(zones.get('require'))
            self.alerts.append(new_alert)

    def load_frigate_config(self, data):
        frigate = data.get('frigate')
        if frigate is not None:
            self.frigate.host = frigate.get('host') or "localhost"
            self.frigate.port = frigate.get('port') or 5000
            self.frigate.use_ssl = frigate.get('ssl') or False

    def load_mqtt_config(self, data):
        mqtt = data.get('mqtt')
        if mqtt is not None:
            self.mqtt.host = mqtt.get('host') or "localhost"
            self.mqtt.port = mqtt.get('port') or 1883
            self.mqtt.listen_topic = mqtt.get('listen_topic') or "#"
            self.mqtt.alert_topic = mqtt.get('alert_topic') or "alerts/camera_system"
            self.mqtt.username = mqtt.get('username')
            self.mqtt.password = mqtt.get('password')

    def __repr__(self):
        return (f"Config(mqtt={self.mqtt}, alerts={self.alerts}, cooldown={self.cooldown}, "
                f"snapshots={self.snapshots}, object_tracking={self.object_tracking})")
    
    def parse_duration(self, duration_str):
        # Update regex pattern to capture float or integer and unit (s = seconds, m = minutes, h = hours)
        pattern = r'(\d*\.?\d+)([smh])'
        match = re.match(pattern, duration_str)
        
        if not match:
            raise ValueError(f"Invalid duration format: {duration_str}")
        
        value, unit = match.groups()
        value = float(value)  # Convert value to float to handle both integers and floats
        
        if unit == 's':  # seconds
            return value
        elif unit == 'm':  # minutes to seconds
            return value * 60
        elif unit == 'h':  # hours to seconds
            return value * 3600
        else:
            raise ValueError(f"Unsupported time unit: {unit}")


class FileBasedAppConfig(AppConfig):
    def __init__(self, config_file, watch_for_changes = True):
        super().__init__()
        self.file_path = Path(config_file).resolve()
        self.reload_function()
        if watch_for_changes:
            self.enable_watchdog()

    def reload_function(self):
        logger.info(f"Loading app configuration from {self.file_path}")
        with open(self.file_path, 'r') as file:
            data = yaml.safe_load(file)
            self.apply_from_dict(data)

    def enable_watchdog(self):
        # Set up the event handler and observer
        file_to_watch = self.file_path
        event_handler = FileChangeHandler(str(file_to_watch), self.reload_function)
        observer = Observer()
        observer.schedule(event_handler, path=str(file_to_watch.parent), recursive=False)

        # Start the observer
        observer.start()
        logger.info(f"Watching configuration file {file_to_watch} for changes...")
        

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, file_path, reload_function):
        self.file_path = file_path
        self.reload_function = reload_function

    def on_modified(self, event):
        if event.src_path == self.file_path:
            logger.info(f"{self.file_path} has been modified, reloading...")
            self.reload_function()
