"""Validate and compile the versioned economy manifest (assortments, prices, jobs)."""

from __future__ import annotations


def build_economy(config: dict, places: list[dict]) -> dict:
    """Validate economy manifest against compiled places and return normalized data for Unreal."""
    if not isinstance(config, dict):
        raise ValueError("economy manifest must be a JSON object")

    starting_money = config.get("starting_money_cents")
    if not isinstance(starting_money, int) or isinstance(starting_money, bool) or starting_money < 0:
        raise ValueError(f"invalid starting_money_cents: {starting_money!r}")
    starting_source = str(config.get("starting_money_source", "")).strip()
    if not starting_source:
        raise ValueError("starting_money_source must be documented")

    economy_seed = int(config.get("economy_seed", 202609))
    places_by_id = {p["id"]: p for p in places}

    assortments_out = []
    seen_categories = set()
    seen_item_ids = set()
    for group in config.get("assortments", []):
        category = str(group.get("category", "")).strip()
        if not category or category in seen_categories:
            raise ValueError(f"duplicate or empty assortment category: {category!r}")
        seen_categories.add(category)

        items_out = []
        for item in group.get("items", []):
            item_id = str(item.get("id", "")).strip()
            if not item_id or item_id in seen_item_ids:
                raise ValueError(f"duplicate or empty item id: {item_id!r}")
            seen_item_ids.add(item_id)

            price = item.get("price_cents")
            if not isinstance(price, int) or isinstance(price, bool) or price <= 0:
                raise ValueError(f"item {item_id} must have integer price_cents > 0, got {price!r}")
            price_source = str(item.get("price_source", "")).strip()
            if not price_source:
                raise ValueError(f"item {item_id} missing price_source")
            name = str(item.get("name", "")).strip()
            if not name:
                raise ValueError(f"item {item_id} missing display name")

            items_out.append({
                "id": item_id,
                "name": name,
                "price_cents": price,
                "price_source": price_source,
            })

        if not items_out:
            raise ValueError(f"assortment category {category!r} has no items")
        assortments_out.append({
            "category": category,
            "items": items_out,
        })

    jobs_out = []
    seen_job_ids = set()
    for job in config.get("jobs", []):
        job_id = str(job.get("id", "")).strip()
        if not job_id or job_id in seen_job_ids:
            raise ValueError(f"duplicate or empty job id: {job_id!r}")
        seen_job_ids.add(job_id)

        place_id = str(job.get("place_id", "")).strip()
        if place_id not in places_by_id:
            raise ValueError(f"job {job_id} references unknown place_id {place_id!r}")

        title = str(job.get("title", "")).strip()
        if not title:
            raise ValueError(f"job {job_id} missing title")

        start_min = job.get("shift_start_minute")
        end_min = job.get("shift_end_minute")
        if (
            not isinstance(start_min, int) or not isinstance(end_min, int)
            or not (0 <= start_min < end_min <= 1440)
        ):
            raise ValueError(f"job {job_id} has invalid shift window {start_min}..{end_min}")

        wage = job.get("hourly_wage_cents")
        if not isinstance(wage, int) or isinstance(wage, bool) or wage <= 0:
            raise ValueError(f"job {job_id} must have integer hourly_wage_cents > 0, got {wage!r}")
        wage_source = str(job.get("wage_source", "")).strip()
        if not wage_source:
            raise ValueError(f"job {job_id} missing wage_source")

        work_days = job.get("work_days", [])
        if not work_days or any(not isinstance(d, int) or not (0 <= d <= 6) for d in work_days):
            raise ValueError(f"job {job_id} has invalid work_days: {work_days!r}")

        jobs_out.append({
            "id": job_id,
            "place_id": place_id,
            "title": title,
            "shift_start_minute": start_min,
            "shift_end_minute": end_min,
            "hourly_wage_cents": wage,
            "work_days": sorted(set(work_days)),
            "wage_source": wage_source,
        })

    return {
        "schema_version": 1,
        "economy_seed": economy_seed,
        "starting_money_cents": starting_money,
        "starting_money_source": starting_source,
        "item_count": len(seen_item_ids),
        "job_count": len(jobs_out),
        "assortments": assortments_out,
        "jobs": jobs_out,
    }
