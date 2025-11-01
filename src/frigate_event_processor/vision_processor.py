"""Provides an abstract class for AI generated vision processors."""

import httpx
import base64
import logging
from abc import ABC, abstractmethod
from .app_configuration import AIConfig, AppConfig
from .event_data import BaseEventData

logger = logging.getLogger(__name__)

class BaseVisionProcessor(ABC):
    """Base class for AI vision processors."""
    def __init__(self, app_config:AppConfig):
        self.app_config = app_config
        self.config = app_config.ai

    @property
    def enabled(self):
        """Returns True if the AI processor is enabled."""
        return self.config.enabled

    @abstractmethod
    def process_event(self, detection:str, location:str, event:BaseEventData):
        """Processes an event using the AI model."""
        raise NotImplementedError("Subclasses must implement this method")
    
    def _fetch_image_base64(self, image_url) -> str:
        """Fetches an image from a URL and returns it as a base64 encoded string."""
        logger.debug("Fetching image from URL: %s", image_url)

        try:
            image_response = httpx.get(image_url)
            if image_response.status_code != 200:
                logger.info("Failed to fetch image from URL [%s]: %s", image_response.status_code, image_url)
                return None
        except httpx.RequestError as exc:
            logger.error("Failed to fetch image from URL: %s: %s", image_url, exc)
            return None

        image_data = image_response.content
        return base64.b64encode(image_data).decode('utf-8')

    def _prepare_prompt(self, detection, location) -> str:
        """Prepares the prompt for the AI model."""
        prompt = self.config.prompt or """Describe this image"""

        if self.config.inject_detection:
            prompt += f"\n\nCamera name was '{location}'. This image was labeled with '{detection}'."

        return prompt
    
    def _get_snapshots_base64(self, event:BaseEventData) -> list:
        snapshot_urls = event.get_snapshot_urls(self.app_config.frigate.api_base_url)
        image_data_base64 = []
        for url in snapshot_urls:
            image_data = super()._fetch_image_base64(url)
            if image_data is not None:
                image_data_base64.append(image_data)
        return image_data_base64
    
    @staticmethod
    def get_vision_engine(app_config: AppConfig) -> 'BaseVisionProcessor':
        """Returns a vision processor based on the engine."""
        engine = app_config.ai.engine
        if engine == 'ollama':
            logger.info("Using Olama Vision processor.")
            from .ollama_vision_processor import OlamaVision
            return OlamaVision(app_config)
        elif engine == 'google':
            logger.info("Using Google Gemini Vision processor.")
            from .google_vision_processor import GoogleVision
            return GoogleVision(app_config)
        else:
            logger.warning(f"Unsupported vision engine: {engine}")
            return None