import copy
import json
import sys
import types
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


try:  # pragma: no cover - dependency shim for test environment
    import watchdog  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    watchdog_module = types.ModuleType('watchdog')
    observers_module = types.ModuleType('watchdog.observers')
    events_module = types.ModuleType('watchdog.events')

    class _Observer:
        def schedule(self, *_args, **_kwargs):
            return None

        def start(self):
            return None

    class _FileSystemEventHandler:
        pass

    observers_module.Observer = _Observer
    events_module.FileSystemEventHandler = _FileSystemEventHandler

    sys.modules['watchdog'] = watchdog_module
    sys.modules['watchdog.observers'] = observers_module
    sys.modules['watchdog.events'] = events_module

try:  # pragma: no cover - dependency shim for PrettyTable
    from prettytable import PrettyTable  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    prettytable_module = types.ModuleType('prettytable')

    class _PrettyTable:
        def __init__(self, *_args, **_kwargs):
            self.field_names = []

        def add_row(self, *_args, **_kwargs):
            return None

        def __str__(self):
            return ''

    prettytable_module.PrettyTable = _PrettyTable
    sys.modules['prettytable'] = prettytable_module

try:  # pragma: no cover - dependency shim for httpx
    import httpx  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    httpx_module = types.ModuleType('httpx')

    class _HttpxResponse:
        status_code = 200
        content = b''

    class _RequestError(Exception):
        pass

    def _httpx_get(*_args, **_kwargs):
        return _HttpxResponse()

    httpx_module.get = _httpx_get
    httpx_module.RequestError = _RequestError
    sys.modules['httpx'] = httpx_module

try:  # pragma: no cover - dependency shim for certifi (transitive request dep)
    import certifi  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    certifi_module = types.ModuleType('certifi')

    def _where():
        return ''

    certifi_module.where = _where
    sys.modules['certifi'] = certifi_module

try:  # pragma: no cover - dependency shim for google-genai
    from google import genai  # type: ignore  # noqa: F401
    from google.genai import types  # type: ignore  # noqa: F401
except (ModuleNotFoundError, ImportError):  # pragma: no cover
    google_module = types.ModuleType('google')
    genai_module = types.ModuleType('google.genai')
    types_module = types.ModuleType('google.genai.types')

    class _Part:
        @staticmethod
        def from_bytes(data, mime_type):
            return {'data': data, 'mime_type': mime_type}

    class _Models:
        def generate_content(self, *args, **kwargs):
            class _Response:
                text = ''

            return _Response()

    class _Client:
        def __init__(self, *args, **kwargs):
            self.models = _Models()

    genai_module.Client = _Client
    types_module.Part = _Part
    genai_module.types = types_module
    google_module.genai = genai_module

    sys.modules['google'] = google_module
    sys.modules['google.genai'] = genai_module
    sys.modules['google.genai.types'] = types_module

from frigate_event_processor.app_configuration import AlertConfig, AppConfig
from frigate_event_processor.frigate_event_processor import (
    EventData,
    EventProcessingQueue,
    FrigateEventProcessor,
)
from frigate_event_processor.vision_processor import BaseVisionProcessor
from frigate_event_processor.google_vision_processor import GoogleVision
from frigate_event_processor.ollama_vision_processor import OlamaVision


def _base_config():
    return {
        'alerts': [
            {
                'camera': 'front_door',
                'labels': ['person'],
            },
        ],
        'mqtt': {
            'host': 'localhost',
            'port': 1883,
            'listen_topic': '#',
            'alert_topic': 'alerts/test',
            'retain': False,
        },
        'frigate': {
            'host': 'localhost',
            'port': 5000,
            'ssl': False,
        },
        'logging': {
            'level': 'INFO',
            'path': None,
        },
        'ai': {
            'engine': 'none',
            'enabled': False,
        },
    }


def make_processor(overrides=None, publish_func=None):
    config_data = copy.deepcopy(_base_config())
    if overrides:
        config_data.update(overrides)
    config = AppConfig()
    config.apply_from_dict(config_data)
    return FrigateEventProcessor(config, publish_func or (lambda *_args, **_kwargs: None))


def make_event(**kwargs):
    start_time = kwargs.get('start_time', datetime.now().timestamp())
    event_data = {
        'id': kwargs.get('event_id', 'event-1'),
        'camera': kwargs.get('camera', 'front_door'),
        'label': kwargs.get('label', 'person'),
        'start_time': start_time,
        'score': kwargs.get('score', 0.75),
        'current_zones': kwargs.get('current_zones', []),
        'entered_zones': kwargs.get('entered_zones', []),
        'has_snapshot': kwargs.get('has_snapshot', True),
        'has_clip': kwargs.get('has_clip', False),
    }
    event = EventData(event_data)
    if 'has_video' in kwargs:
        event.has_video = kwargs['has_video']
    return event


class AlertConfigTests(unittest.TestCase):
    def test_explicit_disabled_flag_respected(self):
        alert = AlertConfig()
        alert.load_json({
            'camera': 'lake_view',
            'labels': ['person'],
            'enabled': False,
        })

        self.assertFalse(alert.enabled)

    def test_enabled_defaults_true_when_missing(self):
        alert = AlertConfig()
        alert.load_json({
            'camera': 'front_door',
            'labels': ['person'],
        })

        self.assertTrue(alert.enabled)

    def test_zone_parsing_for_require_and_ignore(self):
        alert = AlertConfig()
        alert.load_json({
            'camera': 'driveway',
            'labels': ['car'],
            'zones': {
                'require': [
                    {'zone': 'driveway', 'labels': ['car']},
                ],
                'ignore': [
                    {'zone': 'street', 'labels': ['*']},
                ],
            },
        })

        require = alert.zones.require_zones
        ignore = alert.zones.ignore_zones

        self.assertEqual(1, len(require))
        self.assertEqual('driveway', require[0].zone)
        self.assertEqual(['car'], require[0].labels)
        self.assertEqual(1, len(ignore))
        self.assertEqual('street', ignore[0].zone)
        self.assertEqual(['*'], ignore[0].labels)


class CameraGroupConfigTests(unittest.TestCase):
    def test_groups_loaded_from_groups_key(self):
        config = AppConfig()
        config.apply_from_dict({
            'alerts': [],
            'groups': {
                'porch': ['front_door', 'front_steps'],
            },
        })

        group = config.camera_groups.get_camera_group('front_door')
        self.assertIsNotNone(group)
        self.assertEqual('porch', group.name)
        self.assertEqual(['front_door', 'front_steps'], group.cameras)


class CameraGroupCooldownTests(unittest.TestCase):
    def setUp(self):
        config_data = {
            'alerts': [
                {
                    'camera': 'front_door',
                    'labels': ['person'],
                },
            ],
            'groups': {
                'porch': ['front_door', 'front_steps'],
            },
            'alert_rules': {
                'cooldown': {
                    'camera': '0s',
                    'label': '0s',
                    'group': '60s',
                },
            },
            'mqtt': {
                'host': 'localhost',
                'port': 1883,
                'listen_topic': '#',
                'alert_topic': 'alerts/test',
            },
            'frigate': {
                'host': 'localhost',
                'port': 5000,
                'ssl': False,
            },
            'logging': {
                'level': 'INFO',
            },
            'ai': {
                'engine': 'none',
                'enabled': False,
            },
        }
        config = AppConfig()
        config.apply_from_dict(config_data)
        self.processor = FrigateEventProcessor(config, lambda *_args, **_kwargs: None)

    def test_group_cooldown_blocks_recent_notifications(self):
        event = SimpleNamespace(camera='front_door', label='person')
        alert = SimpleNamespace(timestamp=datetime.now())

        self.processor.store_cooldown_for_event(event, alert)

        group = self.processor.config.camera_groups.get_camera_group('front_door')
        self.assertIn(group, self.processor.group_notification_history)
        self.assertFalse(self.processor.is_event_past_cooldown(event))

    def test_group_cooldown_allows_after_duration(self):
        event = SimpleNamespace(camera='front_door', label='person')
        old_alert = SimpleNamespace(timestamp=datetime.now() - timedelta(seconds=120))
        group = self.processor.config.camera_groups.get_camera_group('front_door')
        self.processor.group_notification_history[group] = old_alert

        self.assertTrue(self.processor.is_event_past_cooldown(event))


class CooldownParsingTests(unittest.TestCase):
    def test_parse_durations_across_units(self):
        config = AppConfig()
        config.apply_from_dict({
            'alerts': [],
            'alert_rules': {
                'cooldown': {
                    'camera': '30s',
                    'label': '1m',
                    'group': '2h',
                },
            },
        })

        cooldown = config.alert_rules.cooldown
        self.assertEqual(30, cooldown.camera_duration_seconds)
        self.assertEqual(60, cooldown.label_duration_seconds)
        self.assertEqual(7200, cooldown.group_duration_seconds)

    def test_camera_group_lookup_none_when_unconfigured(self):
        config = AppConfig()
        config.apply_from_dict({
            'alerts': [],
        })

        self.assertIsNone(config.camera_groups.get_camera_group('unknown'))


class CooldownLogicEdgeCaseTests(unittest.TestCase):
    def setUp(self):
        config = AppConfig()
        config.apply_from_dict({
            'alerts': [
                {
                    'camera': 'yard',
                    'labels': ['person'],
                },
            ],
            'alert_rules': {
                'cooldown': {
                    'camera': '0s',
                    'label': '0s',
                },
            },
            'ai': {
                'engine': 'none',
                'enabled': False,
            },
            'logging': {
                'level': 'INFO',
            },
        })
        self.processor = FrigateEventProcessor(config, lambda *_args, **_kwargs: None)

    def test_zero_cooldown_allows_notifications(self):
        event = SimpleNamespace(camera='yard', label='person')
        self.assertTrue(self.processor.is_event_past_cooldown(event))

    def test_invalid_duration_bails_out(self):
        self.processor.config.alert_rules.cooldown.camera_duration_seconds = 'invalid'
        event = SimpleNamespace(camera='yard', label='person')
        self.assertTrue(self.processor.is_event_past_cooldown(event))


class ShouldPublishEventTests(unittest.TestCase):
    def test_rejects_unknown_label(self):
        processor = make_processor()
        event = make_event(label='car')
        self.assertFalse(processor.should_publish_event(None, event))

    def test_requires_zone_absent_blocks_notification(self):
        processor = make_processor({
            'alerts': [
                {
                    'camera': 'front_door',
                    'labels': ['person'],
                    'zones': {
                        'require': [{'zone': 'driveway', 'labels': ['*']}],
                    },
                },
            ],
        })
        event = make_event(current_zones=[])
        self.assertFalse(processor.should_publish_event(None, event))

    def test_required_zone_present_allows(self):
        processor = make_processor({
            'alerts': [
                {
                    'camera': 'front_door',
                    'labels': ['person'],
                    'zones': {
                        'require': [{'zone': 'driveway', 'labels': ['*']}],
                    },
                },
            ],
        })
        event = make_event(current_zones=['driveway'])
        self.assertTrue(processor.should_publish_event(None, event))

    def test_ignored_zone_blocks(self):
        processor = make_processor({
            'alerts': [
                {
                    'camera': 'front_door',
                    'labels': ['person'],
                    'zones': {
                        'ignore': [{'zone': 'street', 'labels': ['*']}],
                    },
                },
            ],
        })
        event = make_event(current_zones=['street'])
        self.assertFalse(processor.should_publish_event(None, event))

    def test_snapshot_requirement_blocks_without_snapshot(self):
        processor = make_processor({
            'alert_rules': {
                'snapshot': True,
            },
        })
        event = make_event(has_snapshot=False)
        self.assertFalse(processor.should_publish_event(None, event))

    def test_video_requirement_blocks_without_video(self):
        processor = make_processor({
            'alert_rules': {
                'video': True,
            },
        })
        event = make_event()
        event.has_video = False
        self.assertFalse(processor.should_publish_event(None, event))

    def test_video_requirement_allows_with_video(self):
        processor = make_processor({
            'alert_rules': {
                'video': True,
            },
        })
        event = make_event()
        event.has_video = True
        self.assertTrue(processor.should_publish_event(None, event))


class EventQueueTests(unittest.TestCase):
    def test_should_queue_when_min_duration_not_met(self):
        processor = make_processor({
            'alert_rules': {
                'min_event_duration': '5s',
            },
        })
        event = make_event(start_time=datetime.now().timestamp())
        self.assertTrue(processor.should_queue_event(event))

    def test_should_not_queue_when_duration_met(self):
        processor = make_processor({
            'alert_rules': {
                'min_event_duration': '5s',
            },
        })
        event = make_event(start_time=(datetime.now() - timedelta(seconds=10)).timestamp())
        self.assertFalse(processor.should_queue_event(event))

    def test_process_end_event_cancels_queue(self):
        processor = make_processor()
        event = make_event(event_id='evt-queue')
        queue = EventProcessingQueue(event)
        queue.timer = MagicMock()
        processor.event_processing_queue[event.id] = queue

        processor.process_end_event({'id': event.id})

        queue.timer.cancel.assert_called_once()
        self.assertNotIn(event.id, processor.event_processing_queue)


class EventTrackingTests(unittest.TestCase):
    def test_event_tracking_payload_published(self):
        publish_calls = []

        def publisher(topic, payload):
            publish_calls.append((topic, payload))

        processor = make_processor({
            'event_tracking': {
                'enabled': True,
                'mqtt_topic': 'frigate_events/cameras',
                'home_assistant_url': 'https://ha.example',
                'home_assistant': False,
            },
        }, publish_func=publisher)

        event = make_event(event_id='evt-track')
        processor.publish_event_to_mqtt(event)

        self.assertEqual(2, len(publish_calls))
        tracking_topic, tracking_payload = publish_calls[1]
        self.assertEqual('frigate_events/cameras/front_door', tracking_topic)
        payload_json = json.loads(tracking_payload)
        self.assertEqual('evt-track', payload_json['event_id'])
        self.assertIn('message', payload_json)


class VisionEngineSelectionTests(unittest.TestCase):
    def test_google_engine_returns_google_vision(self):
        config = AppConfig()
        config.apply_from_dict(_base_config())
        config.ai.load_json({'engine': 'google', 'enabled': False})
        engine = BaseVisionProcessor.get_vision_engine(config.ai)
        self.assertIsInstance(engine, GoogleVision)

    def test_ollama_engine_returns_ollama(self):
        config = AppConfig()
        config.apply_from_dict(_base_config())
        config.ai.load_json({
            'engine': 'ollama',
            'enabled': False,
            'service_url': 'http://localhost:11434',
        })
        engine = BaseVisionProcessor.get_vision_engine(config.ai)
        self.assertIsInstance(engine, OlamaVision)

    def test_unknown_engine_returns_none(self):
        config = AppConfig()
        config.apply_from_dict(_base_config())
        config.ai.load_json({'engine': 'unknown', 'enabled': False})
        engine = BaseVisionProcessor.get_vision_engine(config.ai)
        self.assertIsNone(engine)


if __name__ == '__main__':
    unittest.main()
