"""Send menu labels as well as step IDs, including after frontend cache updates."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=2)
def _translations(language):
    path=Path(__file__).parent/'translations'/f'{language}.json'
    return json.loads(path.read_text(encoding='utf-8'))


def _labels(language,section,step,options):
    english=_translations('en')[section]['step']
    translated=_translations(language)[section]['step']
    fallback=english.get(step,{}).get('menu_options',{})
    labels=translated.get(step,{}).get('menu_options',{})
    return {key:labels.get(key) or fallback.get(key) or translated.get(key,{}).get('title')
            or english.get(key,{}).get('title') or key for key in options}


async def show_menu(flow,section,step,options):
    language=flow.context.get('language') or flow.hass.config.language or 'en'
    language=language.split('-',1)[0].lower()
    if language not in {'de','en'}: language='en'
    labels=await flow.hass.async_add_executor_job(_labels,language,section,step,tuple(options))
    return flow.async_show_menu(step_id=step,menu_options=labels)
