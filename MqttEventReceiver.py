import paho.mqtt.client as mqtt
import os
import json
import sys
import logging
from datetime import datetime
from FrigateEventProcessor import FrigateEventProcessor

from AppConfiguration import AppConfig

logger = logging.getLogger(__name__)

class MqttEventReceiver:
    def __init__(self, config:AppConfig):
        self.config = config
        self.processor = FrigateEventProcessor(config, self.publish_message)
        self.mqtt_client = None

    # Callback when the client receives a message from the server.
    def on_message(self, client, userdata, msg):
        try:
            # Decode the message payload
            message = msg.payload.decode('utf-8')
            
            # Parse the message as JSON
            data = json.loads(message)
            
            # Extract the "after" node if it exists
            self.processor.process_event(data)
        
        except json.JSONDecodeError:
            logger.warning(f"Failed to decode message as JSON from topic {msg.topic}: {message}")

    def publish_message(self, topic, value):
        client = self.mqtt_client
        client.publish(topic, value)

    # Function to connect to the broker and subscribe to the topic
    def connect_and_loop(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_message = self.on_message

        broker = self.config.mqtt.host
        port = self.config.mqtt.port

        logger.info(f"Connecting to broker {broker}:{port}")
        client.connect(broker, port, 60)
        self.mqtt_client = client

        topic = self.config.mqtt.listen_topic
        logger.info(f"Subscribing to topic {topic}")
        client.subscribe(topic)

        # Starts processing the loop on another thread        
        client.loop_start()

        loop = True
        while loop:
            # get user input and respond
            try:
                command = input("")
                if command.lower() == "p":
                    self.processor.print_ongoing_events()
                elif command.lower() == "q":
                    loop = False
            except KeyboardInterrupt:
                logger.info("App received signal to shudown.")
                loop = False

        logger.info("Shutting down...")

        client.loop_stop()
        client.disconnect()
        self.processor.clear_pending_notifications()

        logger.info("Disconnected.")
