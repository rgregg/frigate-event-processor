""" Vision processor that uses a local Olama model to generate image descriptions. """
import logging
import base64
import httpx

from .vision_processor import BaseVisionProcessor
from .app_configuration import AIConfig, AppConfig

logger = logging.getLogger(__name__)

class OlamaVision(BaseVisionProcessor):
    """Class to process images using the local Olama model."""
    def __init__(self, app_config: AppConfig):
        super().__init__(app_config)

    @property
    def enabled(self):
        """Returns True if the AI processor is enabled."""
        return self.config.enabled

    def process_event(self, detection, location, event):
        """Processes an event using the AI model."""
        if not self.config.enabled:
            logger.warning("AI processor is not enabled but was invoked.")
            return None
        
        logger.info("Event %s: processing with AI model: %s", event.id, self.config.ai_model)

        prompt = super()._prepare_prompt(detection, location)
        image_data_base64 = super()._get_snapshots_base64(event)
        request = {
            "model": self.config.ai_model,
            "prompt": prompt,
            "stream": False,
            "images": image_data_base64
        }

        try:
            response = httpx.post(self.config.service_url, json=request)
            logger.debug("API response: %s", response)
            return response.json().get('response')
        except Exception as exc:
            logger.error("Event %s: failed to process image with Olama model: %s", event.id, exc)
            return None