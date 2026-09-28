"""Tiny user-agent summariser: "Chrome on macOS", "Safari on iPhone", "Firefox on Linux"."""

import re

_BROWSERS = [
    ("Edge", r"Edg(e|A|iOS)?/"),
    ("Opera", r"OPR/|Opera"),
    ("Firefox", r"Firefox/|FxiOS/"),
    ("Chrome", r"Chrome/|CriOS/"),
    ("Safari", r"Safari/"),
    ("curl", r"^curl/"),
]

_OSES = [
    ("iPhone", r"iPhone"),
    ("iPad", r"iPad"),
    ("Android", r"Android"),
    ("Windows", r"Windows"),
    ("macOS", r"Mac OS X|Macintosh"),
    ("ChromeOS", r"CrOS"),
    ("Ubuntu", r"Ubuntu"),
    ("Linux", r"Linux"),
]


def describe(ua: str | None) -> str:
    ua = ua or ""
    browser = next((name for name, pat in _BROWSERS if re.search(pat, ua)), None)
    os_name = next((name for name, pat in _OSES if re.search(pat, ua)), None)
    if browser and os_name:
        return f"{browser} on {os_name}"
    return browser or os_name or "Unknown device"
