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
from .frigate_event_processor import FrigateEventProcessor
from .app_configuration import AppConfig
from .hass_discovery import HomeAssistantDiscovery, DiscoverableSensor, DiscoverableImage, DiscoverableDevice, Availability, SensorType, DiscoverableText

logger = logging.getLogger(__name__)

class MqttEventReceiver:
    """A class that handles MQTT message reception, processing, and publishing."""
    
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

        self.register_home_assistant_discovery()

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
                        logger.info("Response %s", message)
                    elif command.lower().startswith("t "):
                        event = self.processor.get_ongoing_event(command[2:])
                        url = self.processor.get_snapshot_url(event)
                        logger.info("Snapshot URL: %s", url)
                    else:
                        option_text = ("p: Print ongoing events\n",
                                       "q: Quit\n",
                                       "a <id>: Generate alert for event ID\n",
                                       "i <id>: Log info for event ID\n",
                                       "n <id>: Generate notification for event ID\n",
                                       "t <id>: Get snapshot URL for event ID\n")
                        logger.info("Unrecognized command. Expected:\n%s", option_text)
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


    def register_home_assistant_discovery(self):
        """ Register the Home Assistant discovery for this service """
        if not self.config.event_tracking.home_assistant:
            return
        
        hass_discovery = HomeAssistantDiscovery(self.config)

        processor_device = DiscoverableDevice("Frigate Event Processor", ["frigate_event_processor"], "Frigate Event Processor", "frigate-event-processor", "1.0", "1.0")
        processor_available = DiscoverableSensor("processor_available", "Processor Running")
        processor_available.state_topic = self.config.mqtt.alert_topic + "/status"
        processor_available.icon = "mdi:server"
        processor_available.device = processor_device
        hass_discovery.publish_sensor(processor_available, self.mqtt_client)

        # Register the MQTT discovery for the event tracking
        camera_names = [alert.camera for alert in self.config.alerts]
        for camera in camera_names:

            device = DiscoverableDevice(f"Event Processor {camera.title()} ", [f"frigate_event_processor_{camera}"], "Frigate Event Processor", "frigate-event-processor", "1.0", "1.0")

            sensor_event_id = DiscoverableSensor(f"{camera}_event_id",
                                        "Last Event ID")
            sensor_event_id.value_template = "{{ value_json.event_id }}"
            sensor_event_id.state_topic = f"{self.config.event_tracking.mqtt_topic}/{camera}"
            sensor_event_id.icon = "mdi:star-box"
            sensor_event_id.device = device
            hass_discovery.publish_sensor(sensor_event_id, self.mqtt_client)

            sensor_event_image = DiscoverableImage(f"{camera}_event_image", 
                                                   "Last Snapshot")
            sensor_event_image.icon = "mdi:image-area"
            sensor_event_image.url_template = "{{ value_json.image_url }}"
            sensor_event_image.device = device
            sensor_event_image.url_topic = f"{self.config.event_tracking.mqtt_topic}/{camera}"
            hass_discovery.publish_sensor(sensor_event_image, self.mqtt_client)

            sensor_message = DiscoverableSensor(f"{camera}_message", 
                                              "Last Event Description")
            sensor_message.value_template = "{{ value_json.message }}"
            sensor_message.state_topic = f"{self.config.event_tracking.mqtt_topic}/{camera}"
            sensor_message.device = device
            hass_discovery.publish_sensor(sensor_message, self.mqtt_client)
        
        logger.info("Home Assistant Discovery registration complete.")

        
