import json
import os
from dataclasses import dataclass, field, replace
from datetime import timedelta

from fsrs import Scheduler

from core import util

DEFAULT_SCHEDULER = Scheduler()


@dataclass(frozen=True)
class ClozeConfig:
    cloze_open: str = "~{"
    cloze_close: str = "}"


@dataclass(frozen=True)
class ReviewConfig:
    cloze: ClozeConfig = field(default_factory=ClozeConfig)
    scheduler_parameters: tuple[float, ...] = DEFAULT_SCHEDULER.parameters
    scheduler_desired_retention: float = DEFAULT_SCHEDULER.desired_retention
    scheduler_learning_steps: tuple[timedelta, ...] = DEFAULT_SCHEDULER.learning_steps
    scheduler_relearning_steps: tuple[timedelta, ...] = DEFAULT_SCHEDULER.relearning_steps
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


def load_review_config() -> ReviewConfig:
    path = util._RUNTIME_CONTEXT.config_path
    defaults = ReviewConfig()
    raw = _load_raw_config(path)
    if raw is None:
        return defaults

    cloze = _parse_cloze_config(_dict_or_empty(raw.get("cloze")), defaults.cloze)
    scheduler_value = raw.get("scheduler")
    scheduler = (
        _parse_scheduler_config(_dict_or_empty(scheduler_value), defaults)
        if isinstance(scheduler_value, dict)
        else None
    )
    if scheduler is None:
        return replace(defaults, cloze=cloze)
    return replace(
        defaults,
        cloze=cloze,
        scheduler_parameters=scheduler.parameters,
        scheduler_desired_retention=scheduler.desired_retention,
        scheduler_learning_steps=scheduler.learning_steps,
        scheduler_relearning_steps=scheduler.relearning_steps,
        scheduler_maximum_interval=scheduler.maximum_interval,
        scheduler_enable_fuzzing=scheduler.enable_fuzzing,
    )


def write_scheduler_parameters(parameters: tuple[float, ...] | list[float]) -> None:
    path = util._RUNTIME_CONTEXT.config_path
    raw = _load_raw_config(path)
    if raw is None:
        raw = {}

    scheduler = dict(_dict_or_empty(raw.get("scheduler")))
    scheduler["parameters"] = list(parameters)
    raw["scheduler"] = scheduler

    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = json.dumps(raw, ensure_ascii=False, indent=4, sort_keys=True)
    util.write_text_atomic(path, payload + "\n")


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


def _parse_cloze_config(cloze_raw: dict[str, object], defaults: ClozeConfig) -> ClozeConfig:
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

    return ClozeConfig(cloze_open=cloze_open, cloze_close=cloze_close)


_SCHEDULER_KEYS = (
    "parameters",
    "desired_retention",
    "learning_steps",
    "relearning_steps",
    "maximum_interval",
    "enable_fuzzing",
)


def _parse_scheduler_config(raw: dict[str, object], defaults: ReviewConfig) -> Scheduler | None:
    scheduler_payload: dict[str, object] = dict(defaults.build_scheduler().to_dict())
    for key in _SCHEDULER_KEYS:
        if key in raw:
            scheduler_payload[key] = raw[key]
    try:
        return Scheduler.from_json(json.dumps(scheduler_payload))
    except (TypeError, ValueError, KeyError):
        return None
