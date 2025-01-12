# MIT License
# Copyright (c) 2025 Ryan Gregg
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Handles MQTT topic registration for Home Assistant MQTT discovery
"""

import logging
import json
from enum import Enum
import paho.mqtt.client as mqtt
from .app_configuration import AppConfig

logger = logging.getLogger(__name__)

class DiscoverableDevice:
    """Class to represent a device that can be discovered by Home Assistant"""
    def __init__(self, name:str, identifiers:list, manufacturer:str, model:str, sw_version:str, hw_version:str):
        self.name = name
        self.identifiers = identifiers
        self.manufacturer = manufacturer
        self.model = model
        self.sw_version = sw_version
        self.hw_version = hw_version

    @staticmethod
    def empty_device():
        """Returns an empty device object"""
        return DiscoverableDevice("", [], "", "", "", "")
    
class Availability:
    """Class to represent the availability of a sensor"""
    def __init__(self, topic:str):
        self.topic = topic
        self.payload_available = "online"
        self.payload_not_available = "offline"
        self.value_template = None

    def to_dict(self) -> dict:
        """Convert the object to a dictionary for JSON serialization"""
        base_dict = {
            "topic": self.topic,
            "payload_available": self.payload_available,
            "payload_not_available": self.payload_not_available,
            "value_template": self.value_template
        }

        #remove any keys with None values
        return {key: value for key, value in base_dict.items() if value is not None}


class SensorType(Enum):
    """Enumeration of sensor types"""
    SENSOR = "sensor"
    # BINARY_SENSOR = "binary_sensor"
    # SWITCH = "switch"
    # FAN = "fan"
    # LIGHT = "light"
    # COVER = "cover"
    # CLIMATE = "climate"
    # VACUUM = "vacuum"
    # CAMERA = "camera"
    IMAGE = "image"
    # LOCK = "lock"
    # DEVICE_TRACKER = "device_tracker"
    # HUMIDIFIER = "humidifier"
    # AIR_QUALITY = "air_quality"
    # WATER_HEATER = "water_heater"
    # WATER_LEVEL = "water_level"
    # WATER_QUALITY = "water_quality"
    # WINDOW = "window"
    # WINDOW_COVERING = "window_covering"
    # ZONE = "zone"
    TEXT = "text"

class DeviceClass(Enum):
    """Enumeration of device classes"""
    ENUM = "enum"
    BATTERY = "battery"
    CONNECTIVITY = "connectivity"
    CURRENT = "current"
    ENERGY = "energy"
    HUMIDITY = "humidity"
    ILLUMINANCE = "illuminance"
    POWER = "power"
    PRESSURE = "pressure"
    SIGNAL_STRENGTH = "signal_strength"
    TEMPERATURE = "temperature"
    TIMESTAMP = "timestamp"
    VOLTAGE = "voltage"

class StateClass(Enum):
    """Enumeration of state classes"""
    DEFAULT = None
    MEASUREMENT = "measurement"
    TOTAL_INCREASING = "total_increasing"
    TOTAL = "total"


class DiscoverableEntityBase:
    """Class to represent common entity components for Home Assistant"""

    def __init__(self, unique_id:str, name:str):
        self._sensor_type = None
        self.name = name
        self.icon = None
        self.enabled_by_default = True
        self._availability = None
        self.device = DiscoverableDevice.empty_device()
        self.unique_id = unique_id
        
    @property
    def sensor_type(self):
        return self._sensor_type
    
    @sensor_type.setter
    def sensor_type(self, value):
        if not isinstance(value, SensorType):
            raise ValueError("sensor_type must be a SensorType")
        self._sensor_type = value

    @property
    def availability(self):
        return self._availability

    @availability.setter
    def availability(self, value):
        if value is None:
            pass
        elif not isinstance(value, Availability):
            raise ValueError("availability must be an Availability")
        self._availability = value

    def to_dict(self):
        """Convert the object to a dictionary for JSON serialization"""
        base_dict = {
            "name": self.name,
            "icon": self.icon,
            "enabled_by_default": self.enabled_by_default,
            "availability": self.availability.to_dict() if self.availability else None,
            "device": {
                "name": self.device.name,
                "identifiers": self.device.identifiers,
                "manufacturer": self.device.manufacturer,
                "model": self.device.model,
                "sw_version": self.device.sw_version,
                "hw_version": self.device.hw_version,
            },
            "unique_id": self.unique_id,
        }
    
        # Remove keys with None values
        return self.remove_none_values(base_dict)
    
    def remove_none_values(self, dictionary: dict):
        """Remove keys with None values from a dictionary"""
        return {key: value for key, value in dictionary.items() if value is not None}

class DiscoverableSensor(DiscoverableEntityBase):
    """Class to represent a sensor that can be discovered by Home Assistant"""

    def __init__(self, unique_id:str, name:str):
        super().__init__(unique_id, name)
        self._sensor_type = SensorType.SENSOR
        self._state_class = None
        self._device_class = None
        self.unit_of_measurement = None
        self.value_template = None
        self.state_topic = None
        self.options = None

    @property
    def device_class(self) -> DeviceClass:
        return self._device_class
    
    @device_class.setter
    def device_class(self, value):
        if not isinstance(value, DeviceClass):
            raise ValueError("device_class must be a DeviceClass")
        self._device_class = value

    @property
    def state_class(self) -> StateClass:
        return self._state_class
    
    @state_class.setter
    def state_class(self, value):
        if not isinstance(value, StateClass):
            raise ValueError("state_class must be a StateClass")
        self._state_class = value

    def to_dict(self):
        """Convert the object to a dictionary for JSON serialization"""
        base_dict = {
            "device_class": self._device_class.value if self._device_class else None,
            "state_class": self._state_class.value if self._state_class else None,
            "unit_of_measurement": self.unit_of_measurement,
            "value_template": self.value_template,
            "state_topic": self.state_topic,
            "options": self.options,
        }
        base_dict.update(super().to_dict())
        return self.remove_none_values(base_dict)

class DiscoverableText(DiscoverableEntityBase):
    """Class to represent a text_input sensor that can be discovered by Home Assistant"""

    def __init__(self, unique_id:str, name:str):
        super().__init__(unique_id, name)
        self._sensor_type = SensorType.TEXT
        self.value_template = None
        self.state_topic = None
        self.command_topic = None
        self.command_template = None

    def to_dict(self):
        """Convert the object to a dictionary for JSON serialization"""
        base_dict = {
            "value_template": self.value_template,
            "state_topic": self.state_topic,
            "command_topic": self.command_topic,
            "command_template": self.command_template,
        }
        base_dict.update(super().to_dict())
        return self.remove_none_values(base_dict)
    


class DiscoverableImage(DiscoverableEntityBase):
    """Class to represent an image sensor that can be discovered by Home Assistant"""
    
    def __init__(self, unique_id:str, name:str):
        super().__init__(unique_id, name)
        self._sensor_type = SensorType.IMAGE
        self.url_topic = None
        self.url_template = None

    def to_dict(self):

        base_dict = {
            "url_topic": self.url_topic,
            "url_template": self.url_template
         }
        base_dict.update(super().to_dict())

        return super().remove_none_values(base_dict)
        
       


class HomeAssistantDiscovery:
    """Class to handle Home Assistant MQTT discovery"""
    def __init__(self, config:AppConfig):
        self.config = config
    
    def publish_sensor(self, sensor:DiscoverableSensor, mqtt_client: mqtt.Client):
        """Publishes HASS discovery information for registered devices"""

        discovery_topic = f"{self.config.event_tracking.discovery_base_topic}/{sensor.sensor_type.value}/{self.clean_key_name(sensor.device.identifiers[0])}/{self.clean_key_name(sensor.unique_id)}/config"
        payload = json.dumps(sensor.to_dict())
        logger.debug("Publishing discovery for %s: %s", discovery_topic, payload)

        mqtt_client.publish(discovery_topic, payload, retain=True)
   
    def clean_key_name(self, value:str):
        """Removes invalid characters from HASS topic names"""
        return value.replace(".", "_").replace(" ", "_").replace(",", "_").replace(":", "_").replace("-", "_")
