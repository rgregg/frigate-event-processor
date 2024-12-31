import logging
import os

from MqttEventReceiver import MqttEventReceiver
from AppConfiguration import FileBasedAppConfig

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