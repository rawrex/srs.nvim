import json
import os
from dataclasses import dataclass, field
from datetime import timedelta

from fsrs import Rating
from fsrs import Scheduler

from core.card import RevealMode


DEFAULT_RATING_BUTTONS: dict[Rating, str] = {
    Rating.Again: "n",
    Rating.Hard: "e",
    Rating.Good: "i",
    Rating.Easy: "o",
}


DEFAULT_SCHEDULER = Scheduler()


@dataclass(frozen=True)
class ClozeConfig:
    reveal_mode: RevealMode = RevealMode.INCREMENTAL
    cloze_open: str = "~{"
    cloze_close: str = "}"
    mask_char: str = "▇"


@dataclass(frozen=True)
class ReviewConfig:
    rating_buttons: dict[Rating, str] = field(
        default_factory=lambda: DEFAULT_RATING_BUTTONS.copy()
    )
    between_notes_timeout_ms: int = 0
    auto_stage_reviewed_cards: bool = False
    show_context: bool = True
    media: str | None = None
    cloze: ClozeConfig = field(default_factory=ClozeConfig)
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
    path = os.path.join(repo_root, ".srs", "config.json")
    defaults = ReviewConfig()
    raw = _load_raw_config(path)
    if raw is None:
        return defaults

    review_raw = _dict_or_empty(raw.get("review"))
    cloze_raw = _dict_or_empty(raw.get("cloze"))
    scheduler_value = raw.get("scheduler")
    scheduler_raw = _dict_or_empty(scheduler_value)

    rating_buttons = _parse_rating_buttons(review_raw.get("rating_buttons"))
    between_notes_timeout_ms, show_context, auto_stage_reviewed_cards = (
        _parse_review_flags(review_raw, defaults)
    )
    cloze_config = _parse_cloze_config(cloze_raw, defaults.cloze)
    media = _parse_media_directory(
        raw.get("media"),
        repo_root,
        defaults.media,
    )
    if media is None:
        media = _parse_media_directory(
            raw.get("attachments_directory"),
            repo_root,
            defaults.media,
        )

    scheduler_parameters = defaults.scheduler_parameters
    scheduler_desired_retention = defaults.scheduler_desired_retention
    scheduler_learning_steps = defaults.scheduler_learning_steps
    scheduler_relearning_steps = defaults.scheduler_relearning_steps
    scheduler_maximum_interval = defaults.scheduler_maximum_interval
    scheduler_enable_fuzzing = defaults.scheduler_enable_fuzzing
    if isinstance(scheduler_value, dict):
        parsed_scheduler = _parse_scheduler_config(scheduler_raw, defaults)
    else:
        parsed_scheduler = None
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
        rating_buttons=rating_buttons,
        between_notes_timeout_ms=between_notes_timeout_ms,
        auto_stage_reviewed_cards=auto_stage_reviewed_cards,
        show_context=show_context,
        media=media,
        cloze=cloze_config,
        scheduler_parameters=scheduler_parameters,
        scheduler_desired_retention=scheduler_desired_retention,
        scheduler_learning_steps=scheduler_learning_steps,
        scheduler_relearning_steps=scheduler_relearning_steps,
        scheduler_maximum_interval=scheduler_maximum_interval,
        scheduler_enable_fuzzing=scheduler_enable_fuzzing,
    )


def _load_raw_config(path: str) -> dict[str, object] | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _dict_or_empty(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def _parse_review_flags(
    review_raw: dict[str, object],
    defaults: ReviewConfig,
) -> tuple[int, bool, bool]:
    between_notes_timeout_ms = defaults.between_notes_timeout_ms
    timeout_raw = review_raw.get("between_notes_timeout_ms")
    if isinstance(timeout_raw, int) and timeout_raw >= 0:
        between_notes_timeout_ms = timeout_raw

    show_context = defaults.show_context
    show_context_raw = review_raw.get("show_context")
    if isinstance(show_context_raw, bool):
        show_context = show_context_raw

    auto_stage_reviewed_cards = defaults.auto_stage_reviewed_cards
    auto_stage_reviewed_cards_raw = review_raw.get("auto_stage_reviewed_cards")
    if isinstance(auto_stage_reviewed_cards_raw, bool):
        auto_stage_reviewed_cards = auto_stage_reviewed_cards_raw

    return between_notes_timeout_ms, show_context, auto_stage_reviewed_cards


def _parse_cloze_config(
    cloze_raw: dict[str, object], defaults: ClozeConfig
) -> ClozeConfig:
    reveal_raw = cloze_raw.get("reveal_mode")
    try:
        reveal_mode = RevealMode(reveal_raw)
    except (TypeError, ValueError):
        reveal_mode = defaults.reveal_mode

    cloze_open = defaults.cloze_open
    cloze_close = defaults.cloze_close
    syntax_raw = cloze_raw.get("syntax")
    if isinstance(syntax_raw, dict):
        maybe_open = syntax_raw.get("open")
        maybe_close = syntax_raw.get("close")
        if isinstance(maybe_open, str) and maybe_open:
            cloze_open = maybe_open
        if isinstance(maybe_close, str) and maybe_close:
            cloze_close = maybe_close

    mask_char = defaults.mask_char
    mask_char_raw = cloze_raw.get("mask_char")
    if isinstance(mask_char_raw, str) and len(mask_char_raw) == 1:
        mask_char = mask_char_raw

    return ClozeConfig(
        reveal_mode=reveal_mode,
        cloze_open=cloze_open,
        cloze_close=cloze_close,
        mask_char=mask_char,
    )


def _parse_media_directory(
    raw_value: object,
    repo_root: str,
    default: str | None,
) -> str | None:
    if not isinstance(raw_value, str):
        return default
    candidate = raw_value.strip()
    if not candidate:
        return default
    if os.path.isabs(candidate):
        return os.path.normpath(candidate)
    return os.path.normpath(os.path.join(repo_root, candidate))


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
