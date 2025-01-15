"""Provides an abstract class for AI generated vision processors."""

import httpx
import base64
import logging
from abc import ABC, abstractmethod
from .app_configuration import AIConfig

logger = logging.getLogger(__name__)

class BaseVisionProcessor(ABC):
    """Base class for AI vision processors."""
    def __init__(self, ai_config):
        self.config = ai_config

    @property
    def enabled(self):
        """Returns True if the AI processor is enabled."""
        return self.config.enabled

    @abstractmethod
    def process_event(self, detection, location, snapshot_url, event):
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

    def _prepare_prompt(self, detection, location):
        """Prepares the prompt for the AI model."""
        prompt = self.config.prompt or """Describe this image"""

        if self.config.inject_detection:
            prompt += f"\n\nCamera name was '{location}'. This image was labeled with '{detection}'."

        return prompt
    
    @staticmethod
    def get_vision_engine(config: AIConfig) -> 'BaseVisionProcessor':
        """Returns a vision processor based on the engine."""
        if config.engine == 'olama':
            logger.info("Using Olama Vision processor.")
            from .ollama_vision_processor import OlamaVision
            return OlamaVision(config)
        elif config.engine == 'google':
            logger.info("Using Google Gemini Vision processor.")
            from .google_vision_processor import GoogleVision
            return GoogleVision(config)
        else:
            logger.warning(f"Unsupported vision engine: {config.engine}")
            return None