from datetime import datetime, timedelta
from typing import Iterable

import logging
import json
from abc import ABC, abstractmethod
from .app_configuration import AlertRulesConfig

logger = logging.getLogger(__name__)

class BaseEventData(ABC):
    def __init__(self, data):
        self.id = data.get('id')
        self.camera = data.get('camera')
        self.start_time = data.get('start_time')
        self.end_time = data.get('end_time')
        self.no_delay = False

    @property
    def duration(self):
        started = datetime.fromtimestamp(self.start_time)
        delta = datetime.now() - started
        return str(delta)
    
    @abstractmethod
    def get_zones(self) -> Iterable[str]:
        pass

    @abstractmethod
    def get_labels(self) -> Iterable[str]:
        pass

    @abstractmethod
    def get_sub_labels(self) -> Iterable[str]:
        pass

    @abstractmethod
    def get_snapshot_urls(self, base_url: str) -> Iterable[str]:
        pass

    @abstractmethod
    def get_thumbnail_urls(self, base_url: str) -> Iterable[str]:
        pass

    @abstractmethod
    def get_video_urls(self, base_url: str) -> Iterable[str]:
        pass
    
    def to_dict(self):
        return self.__dict__

    def __repr__(self):
        return f"Event({json.dumps(self.to_dict(), indent=2)})"
    
    def should_ignore_event(self, config: AlertRulesConfig) -> bool:
        return False
    
    def was_significant_change(self, other: 'BaseEventData') -> bool:
        # Only compare like-with-like
        if not isinstance(other, type(self)):
            raise ValueError("Can't compare different types of events")

        # Normalize zones so order/dupes don't matter
        labels_changed = set(self.get_labels()) != set(other.get_labels())
        sub_labels_changed = set(self.get_sub_labels()) != set(other.get_sub_labels())
        zones_changed = set(self.get_zones()) != set(other.get_zones())
        return any(labels_changed, sub_labels_changed, zones_changed)

class ReviewEventData (BaseEventData):
    def __init__(self, data):
        super().__init__(data)
        self.severity = data.get('severity')
        self.thumb_path = data.get('thumb_path')
        self.data = AlertOrDetectionData(data.get('data'))
        self.no_delay = True    # Disable delays since review detections are already post-processed

    def get_snapshot_urls(self, base_url) -> Iterable[str]:
        return [f"{base_url}/events/{id}/snapshot.jpg" for id in self.data.detections]
    
    def get_thumbnail_urls(self, base_url) -> Iterable[str]:
        return [f"{base_url}/events/{id}/thumbnail.jpg" for id in self.data.detections]
    
    def get_video_urls(self, base_url):
        return [f"{base_url}/events/{id}/clip.mp4" for id in self.data.detections]
    
    def get_labels(self):
        return self.data.objects
    
    def get_sub_labels(self):
        return self.data.sub_labels
    
    def get_zones(self):
        return self.data.zones
    
    def should_ignore_event(self, config: AlertRulesConfig) -> bool:
        if config.minimum_trigger_type == 'detection':
            return self.severity == config.minimum_trigger_type
        return False

class AlertOrDetectionData:
    def __init__(self, data):
        self.detections = data.get('detections')
        self.objects = data.get('objects')
        self.sub_labels = data.get('sub_labels')
        self.zones = data.get('zones')
        self.audio = data.get('audio')

class DetectEventData (BaseEventData):
    def __init__(self, data):
        super.init(data)
        self.frame_time = data.get('frame_time')
        self.snapshot = data.get('snapshot')
        self.label = data.get('label')
        self.sub_label = data.get('sub_label', [])
        self.top_score = data.get('top_score')
        self.score = data.get('score', -1)
        self.box = data.get('box', [])
        self.area = data.get('area')
        self.ratio = data.get('ratio')
        self.region = data.get('region', [])
        self.stationary = data.get('stationary')
        self.motionless_count = data.get('motionless_count')
        self.position_changes = data.get('position_changes')
        self.current_zones = data.get('current_zones', [])
        self.entered_zones = data.get('entered_zones', [])
        self.has_clip = data.get('has_clip', False)
        self.has_snapshot = data.get('has_snapshot', False)

    def get_snapshot_urls(self, base_url) -> Iterable[str]:
        return [base_url + f"/events/{self.id}/snapshot.jpg"]
    
    def get_thumbnail_urls(self, base_url) -> Iterable[str]:
        return [base_url + f"/events/{self.id}/thumbnail.jpg"]
    
    def get_video_urls(self, base_url):
        return [base_url + f"/events/{self.id}/clip.mp4"]
    
    def was_significant_change(self, other: 'BaseEventData') -> bool:
        # Only compare like-with-like
        if not isinstance(other, type(self)):
            raise ValueError("Can't compare different types of events")
        
        # Normalize zones so order/dupes don't matter
        entered_zones_changed = set(self.entered_zones) != set(other.entered_zones)

        # If these can be tri-state (None/False/True), be explicit about the transition
        clip_became_true = (not bool(self.has_clip)) and bool(other.has_clip)
        snap_became_true = (not bool(self.has_snapshot)) and bool(other.has_snapshot)
        super_value = super().was_significant_change(other)

        return any((entered_zones_changed, clip_became_true, snap_became_true, super_value))
