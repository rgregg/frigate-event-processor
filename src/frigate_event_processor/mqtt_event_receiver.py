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
This module defines the MqttEventReceiver class, which is responsible for receiving
and processing MQTT messages. It connects to an MQTT broker, subscribes to a
specified topic, and processes incoming messages using the FrigateEventProcessor 
class. The module also handles publishing messages to the MQTT broker and provides
an interactive command-line interface for managing ongoing events.
Classes:
    MqttEventReceiver: A class that handles MQTT message reception, processing, and publishing.
Functions:
    on_message: Callback when the client receives a message from the server.
    on_connect: Callback when the client connects to the server.
    on_disconnect: Callback when the client disconnects from the server.
    publish_message: Publishes a message to the MQTT broker.
    connect_and_loop: Connects to the MQTT broker and starts the event loop.
"""
import json
import time
import logging
from abc import ABC, abstractmethod
import paho.mqtt.client as mqtt
from .app_configuration import MqttConfig

logger = logging.getLogger(__name__)

class MqttEventProcessor(ABC):
    """Abstract base class for processing MQTT events."""
    @abstractmethod
    def process_mqtt_event(self, _client, _topic:str, _data):
        """Processes an MQTT event for a given topic"""

    @abstractmethod
    def process_mqtt_loop(self, _client)->int:
        """Do work during the event loop for the MQTT client and return how to to pause"""

    @abstractmethod
    def wants_json(self, _client, _topic:str)->bool:
        """Returns True if the processor wants JSON data for process_mqtt_event."""

    @abstractmethod
    def clean_up(self, _client):
        """Clean up any resources used by the processor."""

class MqttConnectionClient:
    """A class that handles MQTT message reception, processing, and publishing."""
    def __init__(self, config:MqttConfig, listen_enabled:bool=True, processor:MqttEventProcessor=None):
        self.listen_enabled = listen_enabled
        self.config = config
        self.mqtt_client = None
        self.processor = processor
        self.status_topic = config.status_topic
        
        # Status values for online and offline modes
        self.ONLINE_STATUS = "online"
        self.OFFLINE_STATUS = "offline"

    # Callback when the client receives a message from the server.
    def on_message(self, _client, _userdata, msg):
        """Callback when the client receives a message from the server."""
        try:
            # Parse the message as JSON
            if (self.processor and self.processor.wants_json(self, msg.topic)):
                message = msg.payload.decode('utf-8')
                data = json.loads(message)
            else:
                data = msg.payload
            
            # Extract the "after" node if it exists
            if self.processor:
                self.processor.process_mqtt_event(self, msg.topic, data)
        
        except json.JSONDecodeError:
            logger.warning("Failed to decode message as JSON from topic %s: %s", msg.topic, message)

    def on_connect(self, client, _userdata, _flags, rc, _properties):
        """Callback when the client connects to the server."""
        logger.info("MQTT session is connected: %s", rc)

        # Subscribe to the topic for events
        if self.listen_enabled:
            topic = self.config.listen_topic
            logger.info("Subscribing to topic %s", topic)
            client.subscribe(topic)
        else:
            logger.debug("MQTT topic listening is disabled.")

        # Publish "online" message when successfully connected
        client.publish(self.status_topic, self.ONLINE_STATUS, retain=True)

    def on_disconnect(self, _client, _userdata, _flags, rc, _properties):
        """Callback when the client disconnects from the server."""
        if rc != 0:
            logger.warning("MQTT session is disconnected: %s", rc)


    def publish_message(self, topic, value, retain=False):
        """Publishes a message to the MQTT broker."""
        client = self.mqtt_client
        client.publish(topic, value, retain=retain)


    def publish_sensor_value(self, topic, value):
        """Publishes a sensor value to the MQTT broker. Automatically adds the sensor topic root."""
        self.publish_message(self.format_sensor_topic(topic), value, retain=True)

    def format_sensor_topic(self, topic):
        """Formats a sensor topic with the sensor topic root."""
        return f"{self.config.sensor_topic_root}/{topic}"

    def connect_and_loop(self):
        """Connects to the MQTT broker and starts the event loop."""
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.will_set(self.status_topic, self.OFFLINE_STATUS, retain=True)
        client.on_message = self.on_message
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect

        broker = self.config.host
        port = self.config.port

        logger.info("Connecting to broker %s:%s", broker, port)
        try:
            client.connect(broker, port, 60)
        except Exception as e:
            logger.error("Unable to connect to server: %s", e)
            raise

        self.mqtt_client = client

        # Starts processing the loop on another thread        
        client.loop_start()

        # Add a signal handler to gracefully shutdown the client
        try:
            while True:
                sleep_until = 1
                if self.processor:
                    sleep_until = self.processor.process_mqtt_loop(self) or sleep_until
                time.sleep(sleep_until)

        except KeyboardInterrupt:
            pass

        logger.info("Shutting down...")
        client.publish(self.status_topic, self.OFFLINE_STATUS, retain=True)

        client.loop_stop()
        client.disconnect()
        self.processor.clean_up(self)

        logger.info("Disconnected.")
