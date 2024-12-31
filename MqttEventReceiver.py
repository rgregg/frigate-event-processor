"""
This module defines the MqttEventReceiver class, which is responsible for receiving and processing MQTT messages.
It connects to an MQTT broker, subscribes to a specified topic, and processes incoming messages using the 
FrigateEventProcessor class. The module also handles publishing messages to the MQTT broker and provides an 
interactive command-line interface for managing ongoing events.
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
import paho.mqtt.client as mqtt
from FrigateEventProcessor import FrigateEventProcessor

from AppConfiguration import AppConfig

logger = logging.getLogger(__name__)

class MqttEventReceiver:
    def __init__(self, config:AppConfig):
        self.config = config
        self.processor = FrigateEventProcessor(config, self.publish_message)
        self.mqtt_client = None

    # Callback when the client receives a message from the server.
    def on_message(self, _client, _userdata, msg):
        """Callback when the client receives a message from the server."""
        try:
            # Decode the message payload
            message = msg.payload.decode('utf-8')
            
            # Parse the message as JSON
            data = json.loads(message)
            
            # Extract the "after" node if it exists
            self.processor.process_event(data)
        
        except json.JSONDecodeError:
            logger.warning("Failed to decode message as JSON from topic %s: %s", msg.topic, message)

    def on_connect(self, client, _userdata, _flags, rc, _properties):
        """Callback when the client connects to the server."""
        logger.info("MQTT session is connected: %s", rc)

        # Subscribe to the topic for events
        topic = self.config.mqtt.listen_topic
        logger.info("Subscribing to topic %s", topic)
        client.subscribe(topic)

        # Publish "online" message when successfully connected
        client.publish(self.config.mqtt.alert_topic + "/status", "online", retain=True)

    def on_disconnect(self, _client, _userdata, _flags, rc, _properties):
        """Callback when the client disconnects from the server."""
        if rc != 0:
            logger.warning("MQTT session is disconnected: %s", rc)


    def publish_message(self, topic, value):
        """Publishes a message to the MQTT broker."""
        client = self.mqtt_client
        client.publish(topic, value)

    def connect_and_loop(self):
        """Connects to the MQTT broker and starts the event loop."""
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.will_set(self.config.mqtt.alert_topic + "/status", "offline", retain=True)
        client.on_message = self.on_message
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect

        broker = self.config.mqtt.host
        port = self.config.mqtt.port

        logger.info("Connecting to broker %s:%s", broker, port)
        try:
            client.connect(broker, port, 60)
        except Exception as e:
            logger.error("Unable to connect to server: %s", e)
            raise

        self.mqtt_client = client

        # Starts processing the loop on another thread        
        client.loop_start()

        loop = True
        skip_input = False
        while loop:
            # get user input and respond
            try:
                if skip_input:
                    time.sleep(1)
                else:
                    command = input("")
                    if command.lower() == "p":
                        self.processor.print_ongoing_events()
                    elif command.lower() == "q":
                        loop = False
                    elif command.lower().startswith("a "):
                        self.processor.generate_alert_for_event_id(command[2:])
                    elif command.lower().startswith("i "):
                        self.processor.log_info_event_id(command[2:])
                    elif command.lower().startswith("n "):
                        event = self.processor.get_ongoing_event(command[2:])
                        message = self.processor.generate_notification(event)
                        logger.info(message)
                    elif command.lower().startswith("t "):
                        event = self.processor.get_ongoing_event(command[2:])
                        url = self.processor.get_snapshot_url(event)
                        logger.info("Snapshot URL: %s", url)
                    else:
                        logger.info("Unrecognized command. Expected: [p, q, a <id>, i <id>, n <id>, t <id>]")
            except EOFError:
                logger.info("App received an EOF from stdin - disabling interactive mode")
                skip_input = True
                
            except KeyboardInterrupt:
                logger.info("App received signal to shudown.")
                loop = False

        logger.info("Shutting down...")
        client.publish(self.config.mqtt.alert_topic + "/status", "offline", retain=True)

        client.loop_stop()
        client.disconnect()
        self.processor.clear_pending_notifications()

        logger.info("Disconnected.")
