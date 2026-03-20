import json
import os
from dataclasses import dataclass
from dataclasses import field
from datetime import timedelta

from fsrs import Rating
from fsrs import Scheduler

from .card import RevealMode


DEFAULT_RATING_BUTTONS: dict[Rating, str] = {
    Rating.Again: "n",
    Rating.Hard: "e",
    Rating.Good: "i",
    Rating.Easy: "o",
}


DEFAULT_SCHEDULER = Scheduler()


@dataclass(frozen=True)
class ReviewConfig:
    reveal_mode: RevealMode = RevealMode.INCREMENTAL
    rating_buttons: dict[Rating, str] = field(
        default_factory=lambda: DEFAULT_RATING_BUTTONS.copy()
    )
    cloze_open: str = "~{"
    cloze_close: str = "}"
    mask_char: str = "▇"
    between_notes_timeout_ms: int = 0
    show_context: bool = True
    context_dim_style: str = "dim"
    scheduler_parameters: tuple[float, ...] = DEFAULT_SCHEDULER.parameters
    scheduler_desired_retention: float = DEFAULT_SCHEDULER.desired_retention
    scheduler_learning_steps: tuple[timedelta, ...] = DEFAULT_SCHEDULER.learning_steps
    scheduler_relearning_steps: tuple[timedelta, ...] = (
        DEFAULT_SCHEDULER.relearning_steps
    )
    scheduler_maximum_interval: int = DEFAULT_SCHEDULER.maximum_interval
    scheduler_enable_fuzzing: bool = DEFAULT_SCHEDULER.enable_fuzzing

    def build_scheduler(self) -> Scheduler:
        return Scheduler(
            parameters=self.scheduler_parameters,
            desired_retention=self.scheduler_desired_retention,
            learning_steps=self.scheduler_learning_steps,
            relearning_steps=self.scheduler_relearning_steps,
            maximum_interval=self.scheduler_maximum_interval,
            enable_fuzzing=self.scheduler_enable_fuzzing,
        )


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

    between_notes_timeout_ms = defaults.between_notes_timeout_ms
    timeout_raw = raw.get("between_notes_timeout_ms")
    if isinstance(timeout_raw, int) and timeout_raw >= 0:
        between_notes_timeout_ms = timeout_raw

    show_context = defaults.show_context
    show_context_raw = raw.get("show_context")
    if isinstance(show_context_raw, bool):
        show_context = show_context_raw

    context_dim_style = defaults.context_dim_style
    context_dim_style_raw = raw.get("context_dim_style")
    if isinstance(context_dim_style_raw, str) and context_dim_style_raw.strip():
        context_dim_style = context_dim_style_raw

    scheduler_raw = raw.get("scheduler")
    scheduler_parameters = defaults.scheduler_parameters
    scheduler_desired_retention = defaults.scheduler_desired_retention
    scheduler_learning_steps = defaults.scheduler_learning_steps
    scheduler_relearning_steps = defaults.scheduler_relearning_steps
    scheduler_maximum_interval = defaults.scheduler_maximum_interval
    scheduler_enable_fuzzing = defaults.scheduler_enable_fuzzing
    if isinstance(scheduler_raw, dict):
        parsed_scheduler = _parse_scheduler_config(scheduler_raw, defaults)
        if parsed_scheduler is not None:
            (
                scheduler_parameters,
                scheduler_desired_retention,
                scheduler_learning_steps,
                scheduler_relearning_steps,
                scheduler_maximum_interval,
                scheduler_enable_fuzzing,
            ) = parsed_scheduler

    return ReviewConfig(
        reveal_mode=reveal_mode,
        rating_buttons=rating_buttons,
        cloze_open=cloze_open,
        cloze_close=cloze_close,
        mask_char=mask_char,
        between_notes_timeout_ms=between_notes_timeout_ms,
        show_context=show_context,
        context_dim_style=context_dim_style,
        scheduler_parameters=scheduler_parameters,
        scheduler_desired_retention=scheduler_desired_retention,
        scheduler_learning_steps=scheduler_learning_steps,
        scheduler_relearning_steps=scheduler_relearning_steps,
        scheduler_maximum_interval=scheduler_maximum_interval,
        scheduler_enable_fuzzing=scheduler_enable_fuzzing,
    )


def _parse_rating_buttons(raw: object) -> dict[Rating, str]:
    if not isinstance(raw, dict):
        return DEFAULT_RATING_BUTTONS.copy()

    parsed: dict[Rating, str] = {}
    for rating in (Rating.Again, Rating.Hard, Rating.Good, Rating.Easy):
        value = raw.get(rating.name)
        if not isinstance(value, str) or len(value) != 1:
            return DEFAULT_RATING_BUTTONS.copy()
        parsed[rating] = value

    if len(set(parsed.values())) != 4:
        return DEFAULT_RATING_BUTTONS.copy()
    return parsed


def _parse_scheduler_config(
    raw: dict[str, object],
    defaults: ReviewConfig,
) -> (
    tuple[
        tuple[float, ...],
        float,
        tuple[timedelta, ...],
        tuple[timedelta, ...],
        int,
        bool,
    ]
    | None
):
    scheduler_payload: dict[str, object] = dict(defaults.build_scheduler().to_dict())
    for key in (
        "parameters",
        "desired_retention",
        "learning_steps",
        "relearning_steps",
        "maximum_interval",
        "enable_fuzzing",
    ):
        if key in raw:
            scheduler_payload[key] = raw[key]
    try:
        scheduler = Scheduler.from_json(json.dumps(scheduler_payload))
    except (TypeError, ValueError, KeyError):
        return None

    return (
        scheduler.parameters,
        scheduler.desired_retention,
        scheduler.learning_steps,
        scheduler.relearning_steps,
        scheduler.maximum_interval,
        scheduler.enable_fuzzing,
    )
