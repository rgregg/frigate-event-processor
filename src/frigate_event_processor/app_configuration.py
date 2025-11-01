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
from abc import ABC, abstractmethod
from typing import Tuple
from pathlib import Path
from .app_config_utils import BaseAppConfig, ParserUtilities

# Define the classes to map the structure
logger = logging.getLogger(__name__)

class BaseConfig(ABC):
    @abstractmethod
    def load_json(self, data):
        pass

    def load_default(self):
        self.load_json({})

    @abstractmethod
    def validate(self):
        pass

class MqttConfig(BaseConfig):
    """Configuration for the MQTT broker"""
    def __init__(self):
        self.host = None
        self.port = None
        self.username = None
        self.password = None
        self.events_topic = None
        self.reviews_topic = None
        self.alert_topic = None
        self.use_reviews = None
        self.load_default()
        self.retain = False
        self.debug = False

    def load_default(self):
        self.load_json({})

    def load_json(self, data):
        """Load saved configuration for the MQTT"""
        self.host = data.get('host') or "localhost"
        self.port = data.get('port') or 1883
        self.events_topic = data.get('events_topic') or data.get('listen_topic') or "frigate/events"
        self.reviews_topic = data.get('reviews_topic') or "frigate/reviews"
        self.use_reviews = data.get('use_reviews') or False
        self.alert_topic = data.get('alert_topic') or "alerts/camera_system"
        self.username = data.get('username')
        self.password = data.get('password')
        self.retain = data.get('retain') or False
        self.debug = data.get('debug') or False
    
    def validate(self):
        if self.use_reviews and not self.reviews_topic:
            raise ValueError("reviews_topic is required when use_reviews=True")
        if not self.use_reviews and not self.events_topic:
            raise ValueError("events_topic is required when use_reviews=False")
        if not self.alert_topic:
            raise ValueError("alert_topic is required.")
        if not self.host:
            raise ValueError("host is required.")
        if not self.port:
            raise ValueError("port is required")
        if self.password and not self.username:
            raise ValueError("username is required if password is set")

    def __repr__(self):
        return f"Mqtt(host={self.host}, username={self.username}, password={self.password}, use_reviews={self.use_reviews}, events_topic={self.events_topic}, reviews_topic={self.reviews_topic}, alert_topic={self.alert_topic})"


class FrigateConfig(BaseConfig):
    """Configuration for the Frigate API"""
    def __init__(self):
        self.host = None
        self.port = None
        self.use_ssl = None
        self.public_host_url = None
        self.load_default()

    def load_default(self):
        self.load_json({})

    def load_json(self, data):
        """Load frigate configuration from a JSON object"""
        self.host = data.get('host') or "localhost"
        self.port = data.get('port') or 5000
        self.use_ssl = data.get('ssl') or False
        self.public_host_url = data.get('public_host_url') or None

    def validate(self):
        if not self.host:
            raise ValueError("frigate host is required.")
        if not self.port:
            raise ValueError("frigate port is required")

    @property
    def api_base_url(self):
        """Get the base URL for the Frigate API"""
        protocol = "https" if self.use_ssl else "http"
        return f"{protocol}://{self.host}:{self.port}/api"
    
    @property
    def public_base_url(self):
        protocol = "https" if self.use_ssl else "http"
        return self.public_host_url or f"{protocol}://{self.host}:{self.port}"
    
    def __repr__(self):
        return f"Frigate(url={self.api_base_url})"

class AlertConfig(BaseConfig):
    """Configuration for alerts"""
    def __init__(self):
        self.camera = None
        self.labels = []
        self.enabled = True
        self.zones = ZonesConfig()
        self.load_default()

    def load_default(self):
        self.load_json({})

    def load_json(self, data):
        """Load alert configuration from a JSON object"""
        self.camera = data.get('camera')
        self.enabled = data.get('enabled') or True
        self.labels = data.get('labels') or []

        zones = data.get('zones')
        if zones is not None:
            self.zones.ignore_zones = ZonesConfig.parse_zones(zones.get('ignore'))
            self.zones.require_zones = ZonesConfig.parse_zones(zones.get('require'))

    def validate(self):
        pass

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
    def check_zone_match(zone_configs: list[ZoneAndLabelsConfig], active_zones: list[str], labels: list[str], default: bool) -> bool:
        """Check if the zone matches the active zones and labels"""
        if zone_configs is None or len(zone_configs) == 0:
            return default
        
        for config in zone_configs:
            # Check if the zone is in active_zones and the label is in the labels of the object
            if config.zone in active_zones:
                # if the label doesn't exist, the zone is enough - otherwise, if the rule has a * or matches the label
                if  "*" in config.labels or labels is None:
                    return True
                label_match = set(labels) & set(config.labels)
                return len(label_match) > 0
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

class CooldownConfig(BaseConfig):
    """Configuration for cooldowns"""
    def __init__(self):
        self.camera_duration_seconds = None
        self.label_duration_seconds = None
        self.group_duration_seconds = None

    def load_default(self):
        self.load_json({})

    def load_json(self, data):
        """Load the cooldown configuration from a JSON object"""
        self.camera_duration_seconds = ParserUtilities.parse_duration(data.get('camera'))
        self.label_duration_seconds = ParserUtilities.parse_duration(data.get('label'))
        self.group_duration_seconds = ParserUtilities.parse_duration(data.get('group'))

        logger.info(f"Cooldown(camera={self.camera_duration_seconds}, object={self.label_duration_seconds}, group={self.group_duration_seconds})")

    def validate(self):
        pass

    def __repr__(self):
        return f"Cooldown(camera={self.camera_duration_seconds}, object={self.label_duration_seconds}, group={self.group_duration_seconds})"

class AlertRulesConfig(BaseConfig):
    """Configuration for alerting rules"""
    def __init__(self):
        self.minimum_duration_seconds = None
        self.maximum_duration_seconds = None
        self.require_snapshot = None
        self.require_video = None
        self.cooldown = CooldownConfig()
        self.minimum_trigger_type = None
        self.load_default()

    def load_default(self):
        self.load_json({})

    def load_json(self, data):
        """Load the alerting rules from a JSON object"""
        self.minimum_duration_seconds = ParserUtilities.parse_duration(data.get('min_event_duration')) 
        self.maximum_duration_seconds = ParserUtilities.parse_duration(data.get('max_event_duration'))
        self.require_snapshot = data.get('snapshot') or False
        self.require_video = data.get('video') or False
        self.minimum_trigger_type = data.get('minimum_trigger_type') or 'alert'

        cooldown = data.get('cooldown')
        if cooldown is not None:
            logger.info("Loading cooldown configuration")
            self.cooldown.load_json(cooldown)
        else:
            logger.info("Using default cooldown configuration")
            self.cooldown.load_default()

    def validate(self):
        if self.minimum_trigger_type == "alert" or self.minimum_trigger_type == "detection":
            pass
        else:
            raise ValueError("minimum_trigger_type must be 'alert' or 'detection'")

    def __repr__(self):
        return f"AlertRules(min_dur={self.minimum_duration_seconds}s, snapshots={self.require_snapshot}, video={self.require_video}, cooldown={self.cooldown})"

class EventTrackingConfig(BaseConfig):
    """Configuration for event tracking"""
    def __init__(self):
        self.enabled = None
        self.mqtt_topic = None
        self.home_assistant = None
        self.discovery_base_topic = None
        self.home_assistant_url = None
        self.image_source = None

    def load_default(self):
        self.load_json({})

    def load_json(self, data):
        """Load the event tracking configuration from a JSON object"""
        self.enabled = data.get('enabled') or False
        self.mqtt_topic = data.get('mqtt_topic')
        self.home_assistant = data.get('home_assistant') or False
        self.discovery_base_topic = data.get('discovery_base_topic') or "homeassistant"
        self.home_assistant_url = data.get('home_assistant_url')
        self.image_source = data.get('image_source') or "frigate"

    def validate(self):
        if self.enabled and not self.mqtt_topic:
            raise ValueError("mqtt_topic is required if enabled.")
        if self.home_assistant and not self.discovery_base_topic:
            raise ValueError("discover_base_topic is required if home_assistant is True")
        if self.home_assistant and not self.home_assistant_url:
            raise ValueError("home_assistant_url is required if home_assistant is True")
        if self.image_source == "ha" and not self.home_assistant_url:
            raise ValueError("image_source: ha requires home_assistant_url to be defined")
        if not self.image_source == "ha" and not self.image_source == "frigate":
            raise ValueError("image_source must be either ha or frigate")

    def __repr__(self):
        return (f"EventTracking(enabled={self.enabled}, mqtt_topic={self.mqtt_topic}, "
            f"home_assistant={self.home_assistant}, discovery_base_topic={self.discovery_base_topic}, "
            f"home_assistant_url={self.home_assistant_url})")

class LoggingConfig(BaseConfig):
    """Configuration for the logger"""
    def __init__(self):
        self.level = None
        self.path = None
        self.rotate = None
        self.max_keep = None
        self.debug = False

    def load_default(self):
        self.load_json({})
    
    def load_json(self, data):
        """Load the logging configuration from a JSON object"""
        self.level = data.get('level') or logging.INFO
        self.path = data.get('path') or None
        self.rotate = data.get('rotate') or False
        self.max_keep = data.get('max_keep') or 10
        self.debug = data.get('debug') or False

    def validate(self):
        pass

class CameraGroupsConfig(BaseConfig):
    """Configuration for camera groups"""
    def __init__(self):
        self.groups = []

    def __repr__(self):
        return f"CameraGroups(groups={self.groups})"
    
    def load_json(self, data):
        """Load the camera groups from a JSON object"""
        self.groups.clear()
        for name, cameras in data.items():
            new_group = CameraGroupConfig()
            new_group.name = name
            new_group.cameras = cameras
            self.groups.append(new_group)
    
    def validate(self):
        pass

    def get_camera_group(self, camera_name: str):
        """Get the camera group that contains the camera"""
        for group in self.groups:
            if camera_name in group.cameras:
                return group
        return None

class CameraGroupConfig:
    """Configuration for a group of cameras"""
    def __init__(self, name: str, cameras: list[str]):
        self.name = name
        self.cameras = cameras

    def __repr__(self):
        return f"CameraGroup(name={self.name}, cameras={self.cameras})"


class AIConfig(BaseConfig):
    """Configuration for the AI model"""
    def __init__(self):
        self.enabled = None
        self.engine = None
        self.api_key = None
        self.ai_model = None
        self.snapshot_format = None
        self.prompt = None
        self.inject_detection = None
        self.service_url = None

    def load_default(self):
        self.load_json({})

    def load_json(self, data):
        """Load the AI configuration from a JSON object"""
        self.enabled = data.get('enabled') or False
        self.engine = data.get('engine') or "google"
        self.api_key = data.get('api_key') or None
        self.ai_model = data.get('ai_model') or "gemini-1.5-flash"
        self.snapshot_format = data.get('snapshot_format') or "image/jpeg"
        self.prompt = data.get('prompt') or None
        self.inject_detection = data.get('inject_detection') or True
        self.service_url = data.get('service_url') or None

    def validate(self):
        if not self.enabled:
            return
        if not self.engine:
            raise ValueError("engine is required if enabled is True")
        if self.engine == "google" and not self.api_key:
            raise ValueError("api_key is required when engine=google")
        if not self.ai_model:
            raise ValueError("ai_model is required if enabled is True")
        if not self.prompt:
            raise ValueError("prompt is required if enabled is True")

    def __repr__(self):
        return f"AIConfig(enabled={self.enabled}, engine={self.engine}, api_key={self.api_key}, ai_model={self.ai_model}, snapshot_format={self.snapshot_format}, prompt={self.prompt}, inject_detection={self.inject_detection}, service_url={self.service_url})"

class AppConfig(BaseAppConfig, BaseConfig):

    """Configuration for the application"""
    def __init__(self):
        self.mqtt = MqttConfig()
        self.frigate = FrigateConfig()
        self.alerts = []
        self.alert_rules = AlertRulesConfig()
        self.event_tracking = EventTrackingConfig()
        self.logging = LoggingConfig()
        self.ai = AIConfig()
        self.camera_groups = CameraGroupsConfig()

    def load_json(self, data):
        """Load settings from a dictionary"""
        self.__load_mqtt_config(data)
        self.__load_frigate_config(data)
        self.__load_alerts_config(data)
        self.__load_rules_config(data)
        self.__load_tracking_config(data)
        self.__load_logging_config(data)
        self.__load_ai_config(data)
        self.__load_camera_groups(data)

    def validate(self):
        self.mqtt.validate()
        self.frigate.validate()
        # self.alerts 
        self.alert_rules.validate()
        self.event_tracking.validate()
        self.logging.validate()
        self.ai.validate()
        self.camera_groups.validate()

    def __load_logging_config(self, data):
        """Load the logging settings"""
        config = data.get('logging')
        if config is not None:
            self.logging.load_json(config)
        else:
            self.logging.load_default()

    def __load_tracking_config(self, data):
        """Load object tracking settings"""
        tracking = data.get('event_tracking')
        if tracking is not None:
            self.event_tracking.load_json(tracking)
        else:
            self.event_tracking.load_default()

    def __load_rules_config(self, data):
        """Load alerting rules"""
        rules = data.get('notification_rules') or data.get('alert_rules')
        if rules is not None:
            self.alert_rules.load_json(rules)
        else:
            self.alert_rules.load_default()

    def __load_alerts_config(self, data):
        """Load alerts configuration"""
        alerts = data.get('notifications') or data.get('alerts')    # Backwards compatible for old config
        self.alerts.clear()
        if alerts is None:
            return
        for alert in alerts:
            new_alert = AlertConfig()
            new_alert.load_json(alert)
            self.alerts.append(new_alert)

    def __load_frigate_config(self, data):
        """Load frigate configuration"""
        frigate = data.get('frigate')
        if frigate is not None:
            self.frigate.load_json(frigate)
        else:
            self.frigate.load_default()

    def __load_mqtt_config(self, data):
        """Load saved configuration for the MQTT"""
        mqtt = data.get('mqtt')
        if mqtt is not None:
            self.mqtt.load_json(mqtt)
        else:
            self.mqtt.load_default()
    
    def __load_ai_config(self, data):
        """Load AI configuration"""
        ai = data.get('ai')
        if ai is not None:
            self.ai.load_json(ai)
        else:
            self.ai.load_default()

    def __load_camera_groups(self, data):
        """Load camera groups"""
        groups = data.get('camera_groups')
        if groups is not None:
            self.camera_groups.load_json(groups)

    def __repr__(self):
        return (f"AppConfig(mqtt={self.mqtt}, frigate={self.frigate}, alerts={self.alerts}, ", 
                f"alert_rules={self.alert_rules}, event_tracking={self.event_tracking}, ", 
                f"logging={self.logging}, ai={self.ai})")
