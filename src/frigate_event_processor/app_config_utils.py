"""
AppConfigurationUtils module
This module provides classes and functions to manage the configuration of an application. It includes support for loading configuration from a YAML file and watching for changes to the configuration file using the watchdog library.
Classes:
    ParserUtilities: Utility functions for parsing configuration values.
    BaseAppConfig: Abstract base class for application configuration.
    FileBasedAppConfig: App configuration that is loaded from a file.
    FileChangeHandler: Event handler for file changes.
Functions:
    ParserUtilities.parse_duration(duration_str): Parse a duration string into seconds.
    FileBasedAppConfig.reload_function(): Reload the configuration from the file.
    FileBasedAppConfig.enable_watchdog(): Enable the watchdog to watch for changes to the configuration file.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
import re
import yaml
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from typing import Generic, TypeVar

# Define the classes to map the structure
logger = logging.getLogger(__name__)


class ParserUtilities:
    """Utility functions for parsing configuration values"""

    @staticmethod
    def parse_duration(duration_str: str) -> float:
        """Parse a duration string into seconds"""

        if duration_str is None:
            return 0.0
        
        # Update regex pattern to capture float or integer and unit (s = seconds, m = minutes, h = hours)
        pattern = r'(\d*\.?\d+)([smh])'
        match = re.match(pattern, duration_str)
        
        if not match:
            raise ValueError(f"Invalid duration format: {duration_str}")
        
        value, unit = match.groups()
        value = float(value)  # Convert value to float to handle both integers and floats
        
        if unit == 's':  # seconds
            return value
        if unit == 'm':  # minutes to seconds
            return value * 60
        if unit == 'h':  # hours to seconds
            return value * 3600
        
        raise ValueError(f"Unsupported time unit: {unit}")

class BaseAppConfig(ABC):
    @abstractmethod
    def apply_from_dict(self, data):
        """Load settings from a dictionary"""
        pass

class FileBasedAppConfig:
    """App configuration that is loaded from a file"""
    def __init__(self, config_object: BaseAppConfig, config_file: str, watch_for_changes = True):
        super().__init__()

        self.__config = config_object
        self.config_file_path = Path(config_file).resolve()
        self.__reload_function()
        if watch_for_changes:
            self.__enable_watchdog()

        

    @property
    def config(self):
        return self.__config

    def __reload_function(self):
        """Reload the configuration from the file"""
        logger.info("Loading app configuration from %s", self.config_file_path)
        with open(self.config_file_path, 'r', encoding='utf-8') as file:
            data = yaml.safe_load(file)
            self.__config.apply_from_dict(data)

    def __enable_watchdog(self):
        """Enable the watchdog to watch for changes to the configuration file"""
        # Set up the event handler and observer
        file_to_watch = self.config_file_path
        event_handler = FileChangeHandler(str(file_to_watch), self.__reload_function)
        observer = Observer()
        observer.schedule(event_handler, path=str(file_to_watch.parent), recursive=False)

        # Start the observer
        observer.start()
        logger.info("Watching configuration file %s for changes...", file_to_watch)
        
class FileChangeHandler(FileSystemEventHandler):
    """Event handler for file changes"""
    def __init__(self, file_to_watch, reload_function):
        self.file_to_watch = file_to_watch
        self.reload_function = reload_function

    def on_modified(self, event):
        if event.src_path == self.file_to_watch:
            logger.info("%s has been modified, reloading...", self.file_to_watch)
            self.reload_function()

