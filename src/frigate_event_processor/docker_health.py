import logging
from threading import Thread
from flask import Flask, jsonify
from abc import ABC, abstractmethod
import os


logger = logging.getLogger(__name__)
app = Flask(__name__)

class BaseHealthCheck(ABC):
    @abstractmethod
    def is_healthy(self) -> bool:
        pass

class DockerHealthCheck:

    @staticmethod
    def health_check_enabled():
        """Checks to see if the Docker health check is enabled."""
        return os.getenv('DOCKER_HEALTH_ENABLED') is not None

    def __init__(self, reference: BaseHealthCheck):
        """
        Initialize the DockerHealthCheck with a custom health check function.

        :param health_check_func: A function that returns a boolean indicating health status
        """
        self.__reference = reference
        # self.__add_routes()
        self.enabled = DockerHealthCheck.health_check_enabled()
        self.host = os.getenv('DOCKER_HEALTH_HOST', '127.0.0.1')
        self.port = os.getenv('DOCKER_HEALTH_PORT', 54123)
        self.__flask_thread = None
        self.__add_routes()

    def run_flask(self):
        # Set Flask logger to only show errors
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        app.run(host=self.host, port=self.port)

    def start(self):
        self.__flask_thread = Thread(target=self.run_flask, daemon=True)
        self.__flask_thread.start()

    def stop(self):
        self.__flask_thread.stop()

    def __add_routes(self):
        """
        Add the Flask route for health checks.
        """
        app.add_url_rule('/health', 'health_check', self.health_check, methods=['GET'])

    def health_check(self):
        """
        Flask route to check the application's health status.
        """
        try:
            is_healthy = self.__reference.is_healthy()
            if is_healthy:
                return jsonify({"status": "healthy"}), 200
            else:
                return jsonify({"status": "unhealthy"}), 500
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({"status": "unhealthy", "error": str(e)}), 500
