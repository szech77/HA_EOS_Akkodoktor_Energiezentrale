"""Send menu labels as well as step IDs, including after frontend cache updates."""
from .flow_translations import _translations, flow_language


def _labels(language,section,step,options):
    english=_translations('en')[section]['step']
    translated=_translations(language)[section]['step']
    fallback=english.get(step,{}).get('menu_options',{})
    labels=translated.get(step,{}).get('menu_options',{})
    return {key:labels.get(key) or fallback.get(key) or translated.get(key,{}).get('title')
            or english.get(key,{}).get('title') or key for key in options}


async def show_menu(flow,section,step,options):
    language=flow_language(flow)
    labels=await flow.hass.async_add_executor_job(_labels,language,section,step,tuple(options))
    if isinstance(options,dict): labels.update({key:value for key,value in options.items() if value is not None})
    return flow.async_show_menu(step_id=step,menu_options=labels)
