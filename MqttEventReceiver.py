import paho.mqtt.client as mqtt
import json
import time
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

    def on_connect(self, client, userdata, flags, rc, properties):
            logger.info(f"MQTT session is connected: {rc}")
            # Publish "online" message when successfully connected
            client.publish(self.config.mqtt.alert_topic + "/status", "online", retain=True)

    def on_disconnect(self, client, userdata, flags, rc, properties):
        if rc != 0:
            logger.warning(f"MQTT session is disconnected: {rc}")


    def publish_message(self, topic, value):
        client = self.mqtt_client
        client.publish(topic, value)

    # Function to connect to the broker and subscribe to the topic
    def connect_and_loop(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.will_set(self.config.mqtt.alert_topic + "/status", "offline", retain=True)
        client.on_message = self.on_message
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect

        broker = self.config.mqtt.host
        port = self.config.mqtt.port

        logger.info(f"Connecting to broker {broker}:{port}")
        try:
            client.connect(broker, port, 60)
        except Exception as e:
            logger.error(f"Unable to connect to server: {e}")
            raise

        self.mqtt_client = client

        topic = self.config.mqtt.listen_topic
        logger.info(f"Subscribing to topic {topic}")
        client.subscribe(topic)

        # Starts processing the loop on another thread        
        client.loop_start()

        loop = True
        skipInput = False
        while loop:
            # get user input and respond
            try:
                if skipInput:
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
                    else:
                        logger.info("Unrecognized command. Expected: [p, q, a <id>, i <id>]")
            except EOFError:
                logger.info("App received an EOF from stdin - disabling interactive mode")
                skipInput = True
                
            except KeyboardInterrupt:
                logger.info("App received signal to shudown.")
                loop = False

        logger.info("Shutting down...")
        client.publish(self.config.mqtt.alert_topic + "/status", "offline", retain=True)

        client.loop_stop()
        client.disconnect()
        self.processor.clear_pending_notifications()

        logger.info("Disconnected.")
