""" Vision processor that uses a local Olama model to generate image descriptions. """
import logging
import base64
import httpx

from .vision_processor import BaseVisionProcessor
from .app_configuration import AIConfig

logger = logging.getLogger(__name__)

class OlamaVision(BaseVisionProcessor):
    """Class to process images using the local Olama model."""
    def __init__(self, ai_config: AIConfig):
        self.config = ai_config

    @property
    def enabled(self):
        """Returns True if the AI processor is enabled."""
        return self.config.enabled

    def process_event(self, detection, location, snapshot_url, event):
        """Processes an event using the AI model."""
        if not self.config.enabled:
            logger.warning("AI processor is not enabled but was invoked.")
            return None
        
        logger.info("Event %s: processing with AI model: %s", event.id, self.config.ai_model)

        image_data = super()._fetch_image_base64(snapshot_url)
        if image_data is None:
            return None

        prompt = super()._prepare_prompt(detection, location)
        
        request = {
            "model": self.config.ai_model,
            "prompt": prompt,
            "stream": False,
            "images": [image_data]
        }

        try:
            response = httpx.post(self.config.service_url, json=request)
            logger.debug("API response: %s", response)
            return response.json().get('response')
        except Exception as exc:
            logger.error("Event %s: failed to process image with Olama model: %s", event.id, exc)
            return None