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
from .app_configuration import AppConfig
from .app_config_utils import FileBasedAppConfig
from .docker_health import DockerHealthCheck

logger = logging.getLogger(__name__)

health_check = None
mqtt_receiver = None

# Main function
def main():
    """Entry point for app"""
    path = os.getenv('CONFIG_FILE', './config.yaml')    
    logger.info("Reading configuration from %s", path)

    config = AppConfig()
    file_config = FileBasedAppConfig(config, path, True)
    logger.debug("Configuration: %s", file_config.config)

    mqtt_receiver = MqttEventReceiver(file_config.config)
    health_check = None
    
    # Start the health check if enabled
    if DockerHealthCheck.health_check_enabled():
        health_check = DockerHealthCheck(mqtt_receiver)
        health_check.start()

    # Start the MQTT event receiver (blocking)
    try:
        mqtt_receiver.connect_and_loop()
    except KeyboardInterrupt:
        logger.info("SIGINT received - Shutting down MQTT event receiver")
        mqtt_receiver.disconnect()
    except Exception as exc:
        logger.error("An unexpdected error occurred: %s", exc)

    # Clean shutdown if we get to this point
    if mqtt_receiver is not None:
        mqtt_receiver.disconnect()
    if health_check is not None:
        health_check.stop()
        


def health_check_func() -> bool:
    """
    Custom health check function for the DockerHealthCheck.

    :return: True if the application is healthy, False otherwise
    """
    if mqtt_receiver is None or not mqtt_receiver.is_connected:
        return False
        
    return True

if __name__ == '__main__':
    main()
