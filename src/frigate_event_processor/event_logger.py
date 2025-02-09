import io
import json

class EventLogger:
    def __init__(self):
        pass

    def log_event(self, event):
        """writes an event out to an event file formatted as a JSON string"""
        with open('raw_event_log.log', 'a') as f:
            json.dump(event, f)
            f.write('\n')