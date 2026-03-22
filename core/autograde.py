from fsrs import Rating


def revealed_ratio(revealed_chars: int, total_chars: int) -> float | None:
    if total_chars <= 0:
        return None
    ratio = revealed_chars / total_chars
    if ratio < 0:
        return 0.0
    if ratio > 1:
        return 1.0
    return ratio


def suggest_rating_from_ratio(revealed: float) -> Rating:
    if revealed < 0.25:
        return Rating.Easy
    if revealed < 0.5:
        return Rating.Good
    if revealed < 0.75:
        return Rating.Hard
    return Rating.Again


def suggest_rating(revealed_chars: int, total_chars: int) -> Rating | None:
    ratio = revealed_ratio(revealed_chars, total_chars)
    if ratio is None:
        return None
    return suggest_rating_from_ratio(ratio)
