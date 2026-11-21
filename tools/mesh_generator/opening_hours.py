"""Parse OpenStreetMap opening_hours strings into a deterministic 7-day schedule."""

from __future__ import annotations

import re


DAY_INDEX = {
    "mo": 0,
    "tu": 1,
    "we": 2,
    "th": 3,
    "fr": 4,
    "sa": 5,
    "su": 6,
}

MONTH_INDEX = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

# Reference month for seasonal OSM opening_hours rules (e.g. "Oct-May: ...; Jun-Sep: ...").
REFERENCE_MONTH = 6  # June (summer season in Doemitz)

TIME_RANGE_RE = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")
MONTH_PREFIX_RE = re.compile(
    r"^\s*([A-Za-z]{3})(?:\s*-\s*([A-Za-z]{3}))?\s*:\s*(.*)$"
)


def _month_in_range(month: int, start_m: int, end_m: int) -> bool:
    if start_m <= end_m:
        return start_m <= month <= end_m
    return month >= start_m or month <= end_m


def _expand_days(day_spec: str) -> list[int]:
    days: list[int] = []
    for token in day_spec.split(","):
        part = token.strip().lower()
        if not part or part in {"ph", "sh"}:
            continue
        if "-" in part:
            bounds = [p.strip() for p in part.split("-", 1)]
            if len(bounds) == 2 and bounds[0] in DAY_INDEX and bounds[1] in DAY_INDEX:
                cur = DAY_INDEX[bounds[0]]
                end = DAY_INDEX[bounds[1]]
                while True:
                    if cur not in days:
                        days.append(cur)
                    if cur == end:
                        break
                    cur = (cur + 1) % 7
        elif part in DAY_INDEX:
            idx = DAY_INDEX[part]
            if idx not in days:
                days.append(idx)
    return days


def _parse_time_ranges(text: str) -> list[list[int]]:
    intervals: list[list[int]] = []
    for match in TIME_RANGE_RE.finditer(text):
        sh, sm, eh, em = (int(match.group(i)) for i in range(1, 5))
        start_min = sh * 60 + sm
        end_min = eh * 60 + em
        if 0 <= start_min < 1440 and 0 < end_min <= 1440 and end_min > start_min:
            intervals.append([start_min, end_min])
    return intervals


def parse_osm_opening_hours(raw: str | None, reference_month: int = REFERENCE_MONTH) -> list[list[list[int]]] | None:
    """Parse an OSM opening_hours string into 7 lists of [start_min, end_min] (0=Mo .. 6=Su).

    Returns None if the string is empty or cannot be parsed into any valid rule.
    """
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip()
    if cleaned == "24/7":
        return [[[0, 1440]] for _ in range(7)]

    # Split into top-level semicolon rules; track active seasonal block.
    days: list[list[list[int]]] = [[] for _ in range(7)]
    parsed_any = False
    season_active = True

    for raw_rule in cleaned.split(";"):
        rule = raw_rule.strip()
        if not rule:
            continue

        # Handle seasonal prefix like "Oct-May: Mo-Th 10:00-15:00"
        m_prefix = MONTH_PREFIX_RE.match(rule)
        if m_prefix and m_prefix.group(1).lower() in MONTH_INDEX:
            start_m = MONTH_INDEX[m_prefix.group(1).lower()]
            end_tok = m_prefix.group(2)
            end_m = MONTH_INDEX[end_tok.lower()] if end_tok and end_tok.lower() in MONTH_INDEX else start_m
            season_active = _month_in_range(reference_month, start_m, end_m)
            rule = m_prefix.group(3).strip()
            if not rule:
                continue

        if not season_active:
            continue

        lower = rule.lower()
        is_off = lower.endswith(" off") or lower.endswith(" closed") or lower in {"off", "closed"}
        if is_off:
            day_part = re.sub(r"\b(off|closed)\b\s*$", "", rule, flags=re.IGNORECASE).strip()
            target_days = _expand_days(day_part) if day_part else list(range(7))
            if target_days:
                for d in target_days:
                    days[d] = []
                parsed_any = True
            continue

        time_match = TIME_RANGE_RE.search(rule)
        if not time_match:
            continue
        day_part = rule[:time_match.start()].strip()
        time_part = rule[time_match.start():].strip()
        intervals = _parse_time_ranges(time_part)
        if not intervals:
            continue
        target_days = _expand_days(day_part) if day_part else list(range(7))
        if not target_days:
            continue
        for d in target_days:
            days[d] = [list(iv) for iv in intervals]
        parsed_any = True

    if not parsed_any:
        return None
    return days


ASSUMED_DEFAULTS: dict[str, tuple[str, list[list[list[int]]]]] = {
    "home": (
        "assumed_home_24_7",
        [[[0, 1440]] for _ in range(7)],
    ),
    "shop": (
        "assumed_shop_default",
        [
            [[480, 1080]],  # Mo 08:00-18:00
            [[480, 1080]],  # Tu
            [[480, 1080]],  # We
            [[480, 1080]],  # Th
            [[480, 1080]],  # Fr
            [[480, 780]],   # Sa 08:00-13:00
            [],             # Su closed
        ],
    ),
    "gastronomy": (
        "assumed_gastronomy_default",
        [[[660, 1260]] for _ in range(7)],  # Mo-Su 11:00-21:00
    ),
    "tourism": (
        "assumed_tourism_default",
        [
            [[600, 1020]],  # Mo-Sa 10:00-17:00
            [[600, 1020]],
            [[600, 1020]],
            [[600, 1020]],
            [[600, 1020]],
            [[600, 1020]],
            [[660, 960]],   # Su 11:00-16:00
        ],
    ),
    "work": (
        "assumed_work_default",
        [
            [[480, 1020]],  # Mo-Fr 08:00-17:00
            [[480, 1020]],
            [[480, 1020]],
            [[480, 1020]],
            [[480, 1020]],
            [],             # Sa closed
            [],             # Su closed
        ],
    ),
}


def resolve_opening_hours(kind: str, osm_opening_hours: str | None = None) -> dict:
    """Resolve opening hours from OSM tag if valid, otherwise return a clearly marked assumption."""
    parsed = parse_osm_opening_hours(osm_opening_hours)
    if parsed is not None:
        return {
            "source": "osm",
            "raw": osm_opening_hours.strip(),
            "always_open": osm_opening_hours.strip() == "24/7",
            "days": parsed,
        }
    assumption_key, default_days = ASSUMED_DEFAULTS.get(kind, ASSUMED_DEFAULTS["work"])
    return {
        "source": assumption_key,
        "raw": "",
        "always_open": kind == "home",
        "days": [[list(iv) for iv in day] for day in default_days],
    }


def is_open_at(opening_hours: dict, day_of_week: int, minute_of_day: float) -> bool:
    """Return True if a compiled opening_hours dict is open at (day_of_week, minute_of_day)."""
    if opening_hours.get("always_open"):
        return True
    days = opening_hours.get("days", [])
    if not (0 <= day_of_week < len(days)):
        return False
    for start_min, end_min in days[day_of_week]:
        if start_min <= minute_of_day < end_min:
            return True
    return False
