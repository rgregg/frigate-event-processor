import logging
import os

from MqttEventReceiver import MqttEventReceiver
from AppConfiguration import FileBasedAppConfig

logger = logging.getLogger(__name__)

# Main function
def main():
    path = os.getenv('CONFIG_FILE', './config.yaml')    
    logger.info(f"Reading configuration from {path}")

    config = FileBasedAppConfig(path, True)
    receiver = MqttEventReceiver(config)
    receiver.connect_and_loop()

if __name__ == '__main__':
    main()