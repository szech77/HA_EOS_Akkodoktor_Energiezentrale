"""Shared native-form translations; file access belongs in the executor."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=2)
def _translations(language):
    path=Path(__file__).parent/'translations'/f'{language}.json'
    return json.loads(path.read_text(encoding='utf-8'))


def flow_language(flow):
    language=flow.context.get('language') or flow.hass.config.language or 'en'
    language=language.split('-',1)[0].lower()
    return language if language in {'de','en'} else 'en'
