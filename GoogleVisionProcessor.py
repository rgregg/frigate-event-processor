import base64
import google.generativeai as genai
import httpx
import logging
from AppConfiguration import AIConfig

logger = logging.getLogger(__name__)

class GoogleVision:
    """Class to process images using Google Vision API."""
    def __init__(self, ai_config: AIConfig):
        self.config = ai_config
        if ai_config.enabled:
            logger.debug("Initializing Google AI with API_KEY: %s", ai_config.api_key)
            genai.configure(api_key=ai_config.api_key)
            ai_model = ai_config.ai_model
            self.model = genai.GenerativeModel(model_name=ai_model)

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
        
        logger.debug("Event %s: fetching image from URL: %s", event.id, snapshot_url)
        try:
            image_response = httpx.get(snapshot_url)
            if image_response.status_code != 200:
                logger.info("Event %s: failed to fetch image from URL: %s", event.id, snapshot_url)
                return None
        except httpx.RequestError as exc:
            logger.error("Event %s: failed to fetch image from URL: %s: %s", event.id, snapshot_url, exc)
            return None
        
        image_data = image_response.content
        prompt = self.config.prompt or """Describe this image"""

        if self.config.inject_detection:
            prompt += f" Camera name was '{location}'. This image was labeled with '{detection}'."
        
        request = [{'mime_type': self.config.snapshot_format, 'data': base64.b64encode(image_data).decode('utf-8')}, prompt]
        logger.debug("API request parameters: %s", request)
        try:
            response = self.model.generate_content(request)
            logger.debug("API response: %s", response)
            return response.text
        except Exception as exc:
            logger.error("Failed to process event %s with AI model: %s: %s", event.id, self.config.ai_model, exc)
            return None
