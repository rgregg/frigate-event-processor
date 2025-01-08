"""
AppConfiguration module
This module provides classes and functions to manage the configuration of an application that integrates with an MQTT broker, Frigate API, and other components. It includes support for loading configuration from a YAML file and watching for changes to the configuration file using the watchdog library.
Classes:
    MqttConfig: Configuration for the MQTT broker.
    FrigateConfig: Configuration for the Frigate API.
    AlertConfig: Configuration for alerts.
    ZoneAndLabelsConfig: Configuration for zones and labels.
    ZonesConfig: Configuration for zones.
    CooldownConfig: Configuration for cooldowns.
    AlertRulesConfig: Configuration for alerting rules.
    ObjectTrackingConfig: Configuration for object tracking.
    LoggingConfig: Configuration for the logger.
    AIConfig: Configuration for the AI model.
    AppConfig: Configuration for the application.
    FileBasedAppConfig: App configuration that is loaded from a file.
    FileChangeHandler: Event handler for file changes.
Functions:
    AppConfig.apply_from_dict(data): Load settings from a dictionary.
    AppConfig.load_logging_config(data): Load the logging settings.
    AppConfig.load_tracking_config(data): Load object tracking settings.
    AppConfig.load_rules_config(data): Load alerting rules.
    AppConfig.load_alerts_config(data): Load alerts configuration.
    AppConfig.load_frigate_config(data): Load frigate configuration.
    AppConfig.load_mqtt_config(data): Load saved configuration for the MQTT.
    AppConfig.load_ai_config(data): Load AI configuration.
    AppConfig.parse_duration(duration_str): Parse a duration string into seconds.
    FileBasedAppConfig.reload_function(): Reload the configuration from the file.
    FileBasedAppConfig.enable_watchdog(): Enable the watchdog to watch for changes to the configuration file.
"""
import logging
from pathlib import Path
import re
import yaml
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Define the classes to map the structure
logger = logging.getLogger(__name__)

class MqttConfig:
    """Configuration for the MQTT broker"""
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
    """Configuration for the Frigate API"""
    def __init__(self):
        self.host = "localhost"
        self.port = 5000
        self.use_ssl = False

    @property
    def api_base_url(self):
        """Get the base URL for the Frigate API"""
        protocol = "https" if self.use_ssl else "http"
        return f"{protocol}://{self.host}:{self.port}/api"
    
    def __repr__(self):
        return f"Frigate(url={self.api_base_url})"

class AlertConfig:
    """Configuration for alerts"""
    def __init__(self, camera):
        self.camera = camera
        self.labels = []
        self.enabled = True
        self.zones = ZonesConfig()

    def __repr__(self):
        return f"Alert(camera={self.camera}, objects={self.labels}, enabled={self.enabled}, zones={self.zones})"

class ZoneAndLabelsConfig:
    """Configuration for zones and labels"""
    def __init__(self):
        self.zone = ""
        self.labels = []

    def __repr__(self):
        return f"ZoneAndLabel(zone={self.zone}, labels={self.labels})"


class ZonesConfig:
    """Configuration for zones"""
    def __init__(self):
        self.ignore_zones = []
        self.require_zones = []

    def __repr__(self):
        return f"Zones(ignored={self.ignore_zones}, required={self.require_zones})"
    
    @staticmethod 
    def check_zone_match(zone_configs: list[ZoneAndLabelsConfig], active_zones: list[str], label: str, default: bool) -> bool:
        """Check if the zone matches the active zones and labels"""
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
        """Parse the zones from the configuration"""
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
    """Configuration for cooldowns"""
    def __init__(self):
        self.camera_duration_seconds = 0
        self.label_duration_seconds = 0

    def __repr__(self):
        return f"Cooldown(camera={self.camera_duration_seconds}, object={self.label_duration_seconds})"

class AlertRulesConfig:
    """Configuration for alerting rules"""
    def __init__(self):
        self.minimum_duration_seconds = 0
        self.maximum_duration_seconds = 0
        self.require_snapshot = False
        self.require_video = False
        self.cooldown = CooldownConfig()

    def __repr__(self):
        return f"AlertRules(min_dur={self.minimum_duration_seconds}s, snapshots={self.require_snapshot}, video={self.require_video}, cooldown={self.cooldown})"

class EventTrackingConfig:
    """Configuration for event tracking"""
    def __init__(self):
        self.enabled = False
        self.mqtt_topic = None
        self.home_assistant = False
        self.discovery_base_topic = "homeassistant"
        self.home_assistant_url = None

    def __repr__(self):
        return f"EventTracking(enabled={self.enabled}, mqtt_topic={self.mqtt_topic})"
    
class LoggingConfig:
    """Configuration for the logger"""
    def __init__(self):
        self.level = logging.INFO
        self.path = None
        self.rotate = False
        self.max_keep = 10

class AIConfig:
    """Configuration for the AI model"""
    def __init__(self):
        self.enabled = False
        self.api_key = None
        self.ai_model = None
        self.snapshot_format = "image/jpeg"
        self.prompt = None
        self.inject_detection = True

    def __repr__(self):
        return f"AIConfig(enabled={self.enabled}, api_key={self.api_key}, ai_model={self.ai_model}, snapshot_format={self.snapshot_format}, prompt={self.prompt}, inject_detection={self.inject_detection})"

class AppConfig:
    """Configuration for the application"""
    def __init__(self):
        self.mqtt = MqttConfig()
        self.frigate = FrigateConfig()
        self.alerts = []
        self.alert_rules = AlertRulesConfig()
        self.event_tracking = EventTrackingConfig()
        self.logging = LoggingConfig()
        self.ai = AIConfig()

    def apply_from_dict(self, data):
        """Load settings from a dictionary"""
        self.load_mqtt_config(data)
        self.load_frigate_config(data)
        self.load_alerts_config(data)
        self.load_rules_config(data)
        self.load_tracking_config(data)
        self.load_logging_config(data)
        self.load_ai_config(data)

    def load_logging_config(self, data):
        """Load the logging settings"""
        log_config = data.get('logging')
        if log_config is not None:
            self.logging.level = log_config.get('level')
            self.logging.path = log_config.get('path')
            self.logging.rotate = log_config.get('rotate')
            self.logging.max_keep = log_config.get('max_keep')

    def load_tracking_config(self, data):
        """Load object tracking settings"""
        tracking = data.get('event_tracking')
        if tracking is not None:
            self.event_tracking.enabled = tracking.get('enabled') or False
            self.event_tracking.mqtt_topic = tracking.get('mqtt_topic')
            self.event_tracking.home_assistant = tracking.get('home_assistant') or False
            self.event_tracking.discovery_base_topic = tracking.get('discovery_base_topic') or "homeassistant"
            self.event_tracking.home_assistant_url = tracking.get('home_assistant_url')
        else:
            self.event_tracking.enabled = False
            self.event_tracking.home_assistant = False

    def load_rules_config(self, data):
        """Load alerting rules"""
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
        """Load alerts configuration"""
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
        """Load frigate configuration"""
        frigate = data.get('frigate')
        if frigate is not None:
            self.frigate.host = frigate.get('host') or "localhost"
            self.frigate.port = frigate.get('port') or 5000
            self.frigate.use_ssl = frigate.get('ssl') or False

    def load_mqtt_config(self, data):
        """Load saved configuration for the MQTT"""
        mqtt = data.get('mqtt')
        if mqtt is not None:
            self.mqtt.host = mqtt.get('host') or "localhost"
            self.mqtt.port = mqtt.get('port') or 1883
            self.mqtt.listen_topic = mqtt.get('listen_topic') or "#"
            self.mqtt.alert_topic = mqtt.get('alert_topic') or "alerts/camera_system"
            self.mqtt.username = mqtt.get('username')
            self.mqtt.password = mqtt.get('password')
    
    def load_ai_config(self, data):
        """Load AI configuration"""
        ai = data.get('ai')
        if ai is not None:
            self.ai.enabled = ai.get('enabled') or False
            self.ai.api_key = ai.get('api_key') or None
            self.ai.ai_model = ai.get('ai_model') or "gemini-1.5-pro"
            self.ai.snapshot_format = ai.get('snapshot_format') or "image/jpeg"
            self.ai.prompt = ai.get('prompt') or None
            self.ai.inject_detection = ai.get('inject_detection') or True

    def __repr__(self):
        return (f"AppConfig(mqtt={self.mqtt}, frigate={self.frigate}, alerts={self.alerts}, alert_rules={self.alert_rules}, event_tracking={self.event_tracking}, logging={self.logging}, ai={self.ai})")
    
    def parse_duration(self, duration_str):
        """Parse a duration string into seconds"""
        # Update regex pattern to capture float or integer and unit (s = seconds, m = minutes, h = hours)
        pattern = r'(\d*\.?\d+)([smh])'
        match = re.match(pattern, duration_str)
        
        if not match:
            raise ValueError(f"Invalid duration format: {duration_str}")
        
        value, unit = match.groups()
        value = float(value)  # Convert value to float to handle both integers and floats
        
        if unit == 's':  # seconds
            return value
        if unit == 'm':  # minutes to seconds
            return value * 60
        if unit == 'h':  # hours to seconds
            return value * 3600
        
        raise ValueError(f"Unsupported time unit: {unit}")


class FileBasedAppConfig(AppConfig):
    """App configuration that is loaded from a file"""
    def __init__(self, config_file, watch_for_changes = True):
        super().__init__()
        self.file_path = Path(config_file).resolve()
        self.reload_function()
        if watch_for_changes:
            self.enable_watchdog()

    def reload_function(self):
        """Reload the configuration from the file"""
        logger.info("Loading app configuration from %s", self.file_path)
        with open(self.file_path, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
            self.apply_from_dict(data)

    def enable_watchdog(self):
        """Enable the watchdog to watch for changes to the configuration file"""
        # Set up the event handler and observer
        file_to_watch = self.file_path
        event_handler = FileChangeHandler(str(file_to_watch), self.reload_function)
        observer = Observer()
        observer.schedule(event_handler, path=str(file_to_watch.parent), recursive=False)

        # Start the observer
        observer.start()
        logger.info("Watching configuration file %s for changes...", file_to_watch)
        

class FileChangeHandler(FileSystemEventHandler):
    """Event handler for file changes"""
    def __init__(self, file_path, reload_function):
        self.file_path = file_path
        self.reload_function = reload_function

    def on_modified(self, event):
        if event.src_path == self.file_path:
            logger.info("%s has been modified, reloading...", self.file_path)
            self.reload_function()
