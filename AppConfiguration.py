import yaml
import logging
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
import re

# Define the classes to map the structure
logger = logging.getLogger(__name__)

class MqttConfig:
    def __init__(self):
        self.host = "localhost"
        self.port = 1883
        self.username = None
        self.password = None
        self.topic = "#"

    def __repr__(self):
        return f"Mqtt(host={self.host}, username={self.username}, password={self.password}, topic={self.topic})"

class FrigateConfig:
    def __init__(self):
        self.host = "localhost"
        self.port = 5000
        self.use_ssl = False

    @property
    def api_base_url(self):
        protocol = "https" if self.use_ssl else "http"
        return f"{protocol}://{self.host}:{self.port}/api"

class AlertConfig:
    def __init__(self, camera):
        self.camera = camera
        self.objects = []
        self.enabled = True
        self.zones = {}

    def __repr__(self):
        return f"Alert(camera={self.camera}, objects={self.objects}, enabled={self.enabled}, zones={self.zones})"

class CooldownConfig:
    def __init__(self):
        self.camera = "0"
        self.object = "0"

    def __repr__(self):
        return f"Cooldown(camera={self.camera}, object={self.object})"

class SnapshotConfig:
    def __init__(self):
        self.required = False

    def __repr__(self):
        return f"Snapshots(required={self.required})"

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
        self.cooldown = CooldownConfig()
        self.snapshots = SnapshotConfig()
        self.object_tracking = ObjectTrackingConfig()
        self.logging = LoggingConfig()

    def apply_from_dict(self, data):
        # Parse mqtt
        mqtt = data.get('mqtt')
        if mqtt is not None:
            self.mqtt.host = mqtt.get('host') or "localhost"
            self.mqtt.port = mqtt.get('port') or 1883
            self.mqtt.topic = mqtt.get('topic') or "#"
            self.mqtt.username = mqtt.get('username')
            self.mqtt.password = mqtt.get('password')

        # Parse frigate
        frigate = data.get('frigate')
        if frigate is not None:
            self.frigate.host = frigate.get('host') or "localhost"
            self.frigate.port = frigate.get('port') or 5000
            self.frigate.use_ssl = frigate.get('ssl') or False

        # Parse alerts
        alerts = data.get('alerts')
        self.alerts.clear()
        for alert in alerts:
            new_alert = AlertConfig(alert.get('camera'))
            new_alert.enabled = alert.get('enabled') or True
            new_alert.objects = alert.get('objects') or []
            new_alert.zones = alert.get('zones') or {}
            self.alerts.append(new_alert)

        # Parse cooldown
        cooldown = data.get('cooldown')
        if cooldown is not None:
            self.cooldown.camera = self.parse_duration(cooldown.get('camera') or "60s")
            self.cooldown.object = self.parse_duration(cooldown.get('object') or "60s")
        else:
            self.cooldown.camera = 60
            self.cooldown.object = 60
        
        # Parse snapshots
        snapshots = data.get('snapshots')
        if snapshots is not None:
            self.snapshots.required = snapshots.get('required')
        else:
            self.snapshots.required = False
        
        # Parse object tracking
        tracking = data.get('object_tracking')
        if tracking is not None:
            self.object_tracking.enabled = tracking.get('enabled')
        else:
            self.object_tracking.enabled = True

        # Parse logger
        logging = data.get('logging')
        if logging is not None:
            self.logging.level = logging.get('level')
            self.logging.path = logging.get('path')
            self.logging.rotate = logging.get('rotate')
            self.logging.max_keep = logging.get('max_keep')

    def __repr__(self):
        return (f"Config(mqtt={self.mqtt}, alerts={self.alerts}, cooldown={self.cooldown}, "
                f"snapshots={self.snapshots}, object_tracking={self.object_tracking})")
    
    def parse_duration(self, duration_str):
        # Define regex pattern to capture number and unit (s = seconds, m = minutes, h = hours)
        pattern = r'(\d+)([smh])'
        match = re.match(pattern, duration_str)
        
        if not match:
            raise ValueError(f"Invalid duration format: {duration_str}")
        
        value, unit = match.groups()
        value = int(value)
        
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
