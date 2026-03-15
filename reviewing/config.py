import json
import os
from dataclasses import dataclass
from dataclasses import field
from typing import Dict

from fsrs import Rating

from .card import RevealMode


DEFAULT_RATING_BUTTONS: Dict[Rating, str] = {
    Rating.Again: "n",
    Rating.Hard: "e",
    Rating.Good: "i",
    Rating.Easy: "o",
}


@dataclass(frozen=True)
class ReviewConfig:
    reveal_mode: RevealMode = RevealMode.INCREMENTAL
    rating_buttons: Dict[Rating, str] = field(
        default_factory=lambda: DEFAULT_RATING_BUTTONS.copy()
    )
    cloze_open: str = "~{"
    cloze_close: str = "}"
    mask_char: str = "▇"


def load_review_config(repo_root: str) -> ReviewConfig:
    path = os.path.join(repo_root, "config.json")
    defaults = ReviewConfig()
    if not os.path.exists(path):
        return defaults

    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(raw, dict):
        return defaults

    reveal_raw = raw.get("reveal_mode")
    try:
        reveal_mode = RevealMode(reveal_raw)
    except (TypeError, ValueError):
        reveal_mode = defaults.reveal_mode
    rating_buttons = _parse_rating_buttons(raw.get("rating_buttons"))

    cloze_raw = raw.get("cloze_syntax")
    cloze_open = defaults.cloze_open
    cloze_close = defaults.cloze_close
    if isinstance(cloze_raw, dict):
        maybe_open = cloze_raw.get("open")
        maybe_close = cloze_raw.get("close")
        if isinstance(maybe_open, str) and maybe_open:
            cloze_open = maybe_open
        if isinstance(maybe_close, str) and maybe_close:
            cloze_close = maybe_close

    mask_char = defaults.mask_char
    mask_char_raw = raw.get("mask_char")
    if isinstance(mask_char_raw, str) and len(mask_char_raw) == 1:
        mask_char = mask_char_raw

    return ReviewConfig(
        reveal_mode=reveal_mode,
        rating_buttons=rating_buttons,
        cloze_open=cloze_open,
        cloze_close=cloze_close,
        mask_char=mask_char,
    )


def _parse_rating_buttons(raw: object) -> Dict[Rating, str]:
    if not isinstance(raw, dict):
        return DEFAULT_RATING_BUTTONS.copy()

    parsed: Dict[Rating, str] = {}
    for rating in (Rating.Again, Rating.Hard, Rating.Good, Rating.Easy):
        value = raw.get(rating.name)
        if not isinstance(value, str) or len(value) != 1:
            return DEFAULT_RATING_BUTTONS.copy()
        parsed[rating] = value

    if len(set(parsed.values())) != 4:
        return DEFAULT_RATING_BUTTONS.copy()
    return parsed
