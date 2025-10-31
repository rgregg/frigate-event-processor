"""Module to process images using Google Vision API."""

import logging
import base64
import google.generativeai as genai
import httpx

from .event_data import BaseEventData
from .vision_processor import BaseVisionProcessor
from .app_configuration import AIConfig, AppConfig

logger = logging.getLogger(__name__)

class GoogleVision(BaseVisionProcessor):
    """Class to process images using Google Vision API."""
    def __init__(self, app_config: AppConfig):
        super().__init__(app_config)
        ai_config = app_config.ai
        if ai_config.enabled:
            logger.debug("Initializing Google AI")
            genai.configure(api_key=ai_config.api_key)
            ai_model = ai_config.ai_model
            logger.debug("Specified model: %s", ai_model)
            self.model = genai.GenerativeModel(model_name=ai_model)
            logger.info("Google AI model initialized: %s", ai_model)

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

        request = [super()._prepare_prompt(detection, location)]
        image_data_base64 = super()._get_snapshots_base64(event)
        for image_data in image_data_base64:
            if len(image_data_base64) > 0:
                request.insert(0, {'mime_type': self.config.snapshot_format, 'data': image_data})

        logger.debug("API request parameters: %s", request)
        try:
            response = self.model.generate_content(request)
            logger.debug("API response: %s", response)
            return response.text
        except Exception as exc:
            logger.error("Failed to process event %s with AI model: %s: %s", event.id, self.config.ai_model, exc)
            return None
