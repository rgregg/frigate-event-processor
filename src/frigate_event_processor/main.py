"""
mqtt_processor.py

This module sets up and runs an MQTT event processor. It reads configuration
from a specified file, initializes the application configuration, and starts
an MQTT event receiver to process incoming events.

Modules:
    logging: Provides logging capabilities.
    os: Provides a way of using operating system dependent functionality.
    MqttEventReceiver: Handles receiving events from an MQTT broker.
    AppConfiguration: Manages application configuration from a file.

Functions:
    main: Entry point for the application. Reads configuration, initializes
          the MQTT event receiver, and starts the event loop.
"""
import logging
import os

from .mqtt_event_receiver import MqttEventReceiver
from .app_configuration import FileBasedAppConfig

logger = logging.getLogger(__name__)

# Main function
def main():
    """Entry point for app"""
    path = os.getenv('CONFIG_FILE', './config.yaml')    
    logger.info("Reading configuration from %s", path)

    config = FileBasedAppConfig(path, True)

    logger.debug("Configuration: %s", config)

    receiver = MqttEventReceiver(config)
    receiver.connect_and_loop()

if __name__ == '__main__':
    main()
