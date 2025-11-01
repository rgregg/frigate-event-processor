import httpx
import os

if __name__ == "__main__":
    
    is_enabled = os.getenv('DOCKER_HEALTH_ENABLED') is not None
    host = os.getenv('DOCKER_HEALTH_HOST', 'localhost')
    port = os.getenv('DOCKER_HEALTH_PORT', 8000)
    
    if is_enabled:
        response = httpx.get(f"http://{host}:{port}/health")
        if response.status_code != 200:
            # exit with failure
            exit(1)
            
    exit(0)
