import logging
from threading import Thread
from flask import Flask, jsonify
from abc import ABC, abstractmethod
import os
from werkzeug.serving import make_server


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
        self.port = int(os.getenv('DOCKER_HEALTH_PORT', '54123'))
        self.__server = None
        self.__thread = None
        self.__add_routes()

    def start(self):
        if not self.enabled:
            return

        if self.__server is not None:
            logger.debug("Docker health server already running")
            return

        # Build a WSGI server we can shut down later
        self.__server = make_server(self.host, self.port, app)

        # Keep Werkzeug's request logs quiet
        logging.getLogger('werkzeug').setLevel(logging.ERROR)

        # Serve in a background thread
        self.__thread = Thread(target=self.__server.serve_forever, daemon=True)
        self.__thread.start()
        logger.info(f"Docker health server started on {self.host}:{self.port}")

    def stop(self):
        if not self.enabled:
            return

        if self.__server is None:
            logger.debug("Docker health server is not running")
            return

        try:
            self.__server.shutdown()
            if self.__thread is not None:
                self.__thread.join(timeout=2)
            logger.info("Docker health server stopped")
        finally:
            self.__server = None
            self.__thread = None

    def __add_routes(self):
        """
        Add the Flask route for health checks.
        """
        if not self.enabled:
            return

        app.add_url_rule('/health', 'health_check', self.health_check, methods=['GET'])

    def health_check(self):
        """
        Flask route to check the application's health status.
        """

        if not self.enabled:
            return

        try:
            is_healthy = self.__reference.is_healthy()
            if is_healthy:
                return jsonify({"status": "healthy"}), 200
            else:
                return jsonify({"status": "unhealthy"}), 500
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({"status": "unhealthy", "error": str(e)}), 500
