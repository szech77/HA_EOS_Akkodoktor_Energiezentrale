"""Load the UI language pack selected in the Supervisor configuration."""
import json
import re
from pathlib import Path


PACKS = Path(__file__).with_name("i18n")
LANGUAGE_TAG = re.compile(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\Z")


def load_language(language="auto", directory=PACKS, *, ha_language=None):
    def read(code):
        path = directory / (code + ".json")
        data = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or not isinstance(data.get("locale"), str)
                or not LANGUAGE_TAG.fullmatch(data["locale"])
                or not isinstance(data.get("messages"), dict)
                or not all(isinstance(value, str) and value for value in data["messages"].values())):
            raise ValueError("Ungültiges Sprachpaket")
        return data

    default = read("en")
    requested = ha_language if language == "auto" else language
    if not isinstance(requested, str) or not LANGUAGE_TAG.fullmatch(requested):
        return default
    for code in dict.fromkeys((requested, requested.split("-")[0])):
        if code == "en":
            return default
        try:
            selected = read(code)
        except (FileNotFoundError, ValueError, TypeError):
            continue
        return {"locale": selected["locale"], "messages": {**default["messages"], **selected["messages"]}}
    return default
