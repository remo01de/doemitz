"""Validate and compile the versioned daily task templates manifest."""

from __future__ import annotations


VALID_TASK_TYPES = {"errand", "fetch"}


def build_tasks(config: dict, places: list[dict], economy: dict | None) -> dict:
    """Validate task templates against compiled places and economy items."""
    if not isinstance(config, dict):
        raise ValueError("tasks manifest must be a JSON object")

    task_seed = int(config.get("task_seed", 202610))
    daily_min = int(config.get("daily_min_tasks", 3))
    daily_max = int(config.get("daily_max_tasks", 5))
    if daily_min < 1 or daily_max < daily_min:
        raise ValueError(f"invalid daily task bounds: {daily_min}..{daily_max}")

    places_by_id = {p["id"]: p for p in places}
    items_by_id: dict[str, dict] = {}
    item_categories: dict[str, set[str]] = {}
    if economy:
        for group in economy.get("assortments", []):
            cat = group["category"]
            for item in group.get("items", []):
                items_by_id[item["id"]] = item
                item_categories.setdefault(item["id"], set()).add(cat)

    templates_out = []
    seen_ids = set()
    for tpl in config.get("templates", []):
        tpl_id = str(tpl.get("id", "")).strip()
        if not tpl_id or tpl_id in seen_ids:
            raise ValueError(f"duplicate or empty task template id: {tpl_id!r}")
        seen_ids.add(tpl_id)

        ttype = str(tpl.get("type", "")).strip().lower()
        if ttype not in VALID_TASK_TYPES:
            raise ValueError(f"task template {tpl_id} has invalid type {ttype!r}")

        title = str(tpl.get("title", "")).strip()
        description = str(tpl.get("description", "")).strip()
        if not title or not description:
            raise ValueError(f"task template {tpl_id} missing title or description")

        duration_min = tpl.get("duration_minutes")
        if not isinstance(duration_min, int) or isinstance(duration_min, bool) or not (15 <= duration_min <= 720):
            raise ValueError(f"task template {tpl_id} has invalid duration_minutes: {duration_min!r}")

        reward = tpl.get("reward_cents")
        if not isinstance(reward, int) or isinstance(reward, bool) or reward <= 0:
            raise ValueError(f"task template {tpl_id} must have integer reward_cents > 0, got {reward!r}")

        reward_source = str(tpl.get("reward_source", "")).strip()
        if not reward_source:
            raise ValueError(f"task template {tpl_id} missing reward_source")

        pickup_id = ""
        delivery_id = ""
        parcel_name = ""
        requested_item_id = ""
        preferred_shop_id = ""

        if ttype == "errand":
            pickup_id = str(tpl.get("pickup_place_id", "")).strip()
            delivery_id = str(tpl.get("delivery_place_id", "")).strip()
            parcel_name = str(tpl.get("parcel_name", "")).strip()
            if pickup_id not in places_by_id:
                raise ValueError(f"errand {tpl_id} references unknown pickup_place_id {pickup_id!r}")
            if delivery_id not in places_by_id:
                raise ValueError(f"errand {tpl_id} references unknown delivery_place_id {delivery_id!r}")
            if pickup_id == delivery_id:
                raise ValueError(f"errand {tpl_id} pickup and delivery places must differ")
            if not parcel_name:
                raise ValueError(f"errand {tpl_id} missing parcel_name")
        elif ttype == "fetch":
            requested_item_id = str(tpl.get("requested_item_id", "")).strip()
            preferred_shop_id = str(tpl.get("preferred_shop_place_id", "")).strip()
            if requested_item_id not in items_by_id:
                raise ValueError(f"fetch {tpl_id} references unknown requested_item_id {requested_item_id!r}")
            if preferred_shop_id not in places_by_id:
                raise ValueError(f"fetch {tpl_id} references unknown preferred_shop_place_id {preferred_shop_id!r}")
            shop_place = places_by_id[preferred_shop_id]
            shop_cat = shop_place.get("economy_category") or shop_place.get("kind")
            valid_cats = item_categories.get(requested_item_id, set())
            if shop_cat not in valid_cats and shop_place.get("kind") not in valid_cats:
                raise ValueError(
                    f"fetch {tpl_id} shop {preferred_shop_id} (cat={shop_cat}) does not sell {requested_item_id}"
                )

        templates_out.append({
            "id": tpl_id,
            "type": ttype,
            "title": title,
            "description": description,
            "pickup_place_id": pickup_id,
            "delivery_place_id": delivery_id,
            "parcel_name": parcel_name,
            "requested_item_id": requested_item_id,
            "preferred_shop_place_id": preferred_shop_id,
            "duration_minutes": duration_min,
            "reward_cents": reward,
            "reward_source": reward_source,
        })

    if len(templates_out) < daily_min:
        raise ValueError(f"need at least {daily_min} task templates, got {len(templates_out)}")

    return {
        "schema_version": 1,
        "task_seed": task_seed,
        "daily_min_tasks": daily_min,
        "daily_max_tasks": daily_max,
        "template_count": len(templates_out),
        "errand_count": sum(1 for t in templates_out if t["type"] == "errand"),
        "fetch_count": sum(1 for t in templates_out if t["type"] == "fetch"),
        "templates": templates_out,
    }
