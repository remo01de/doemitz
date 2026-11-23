"""Sprint 13.1 PIE check: street lamps, benches and tree trunks block the player, foliage and the Visibility
channel do not. The player walks straight at one free-standing instance of each kind and must stop at the
collision radius instead of walking through it."""

from math import cos, hypot, radians, sin
from time import monotonic
import traceback

import unreal

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

BLOCKING = (
    "Altstadt HISM Lamps Metal", "Altstadt HISM Benches", "Altstadt HISM Planters", "Altstadt HISM Bollards",
    "Altstadt HISM Trees 0", "Altstadt HISM Trees 1", "Altstadt HISM Trees 2",
)
WALK_THROUGH = ("Altstadt HISM Lamps Glow", "Altstadt HISM Bushes 0", "Altstadt HISM Bushes 1", "Altstadt HISM Bushes 2")
# (label prefix, collision radius / half depth in cm at scale 1, approach along the mesh Y axis = bench front)
WALK_TESTS = (
    ("Altstadt HISM Lamps Metal", 16.0, False),
    ("Altstadt HISM Benches", 27.0, True),
    ("Altstadt HISM Trees", 26.0, False),
)
START_DIST_CM = 260.0
WALK_SECONDS = 2.6

deadline = monotonic() + 150
phase = "init"
test_index = 0
walk_start = 0.0
current = None
results = []
pawn_seen = None


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def trace_ground(world, x, y, z, ignore):
    hit = unreal.SystemLibrary.line_trace_single(
        world, unreal.Vector(x, y, z + 300.0), unreal.Vector(x, y, z - 300.0),
        unreal.TraceTypeQuery.ECC_VISIBILITY, False, ignore, unreal.DrawDebugTrace.NONE, False,
    )
    return hit.to_dict() if hit is not None else None


def prop_actors(world):
    found = {}
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.DoemitzInstancedPropActor):
        found[actor.get_actor_label()] = actor
    return found


def instances(actor):
    comp = actor.get_editor_property("hism_component")
    for i in range(comp.get_instance_count()):
        t = comp.get_instance_transform(i, True)
        if isinstance(t, tuple):
            t = t[-1]
        if t is not None:
            yield i, t


def pick_candidate(world, pawn, actor, radius_cm, along_y):
    """First instance with flat walkable ground on one approach side and nothing but the prop in between."""
    cap = pawn.get_editor_property("capsule_component")
    pr = cap.get_scaled_capsule_radius()
    ph = cap.get_scaled_capsule_half_height()
    objects = [unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY1, unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY2,
               unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY3]
    for _, t in instances(actor):
        c = t.translation
        scale = t.scale3d.x
        if along_y:
            y_axis = unreal.MathLibrary.transform_direction(t, unreal.Vector(0.0, 1.0, 0.0))
            dirs = [unreal.Vector(y_axis.x, y_axis.y, 0.0), unreal.Vector(-y_axis.x, -y_axis.y, 0.0)]
        else:
            dirs = [unreal.Vector(cos(radians(a)), sin(radians(a)), 0.0) for a in range(0, 360, 45)]
        g0 = trace_ground(world, c.x, c.y, c.z, [pawn, actor])
        if g0 is None or abs(g0["impact_point"].z - c.z) > 30.0:
            continue
        for d in dirs:
            d = d.normal()
            sx, sy = c.x + d.x * START_DIST_CM, c.y + d.y * START_DIST_CM
            g = trace_ground(world, sx, sy, c.z, [pawn, actor])
            if g is None or abs(g["impact_point"].z - c.z) > 25.0 or g["impact_normal"].z < 0.95:
                continue
            gz = g["impact_point"].z
            start = unreal.Vector(sx, sy, gz + ph + 12.0)
            end = unreal.Vector(c.x, c.y, gz + ph + 12.0)
            hit = unreal.SystemLibrary.capsule_trace_single_for_objects(
                world, start, end, pr, ph, objects, False, [pawn], unreal.DrawDebugTrace.NONE, True,
            )
            if hit is None:
                continue
            h = hit.to_dict()
            if h["hit_actor"] != actor or h.get("initial_overlap"):
                continue
            return {"center": c, "start": start, "expected": radius_cm * scale + pr, "scale": scale}
    return None


def tick(_dt):
    global phase, test_index, walk_start, current, pawn_seen
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out in phase {phase} at test {test_index}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0) if world else None
        if pawn is None:
            return
        if pawn_seen is None:
            pawn_seen = monotonic()
        if phase == "init":
            # let PIE settle (pawn possessed, first ground contact) before walking
            if monotonic() - pawn_seen < 3.0:
                return
            actors = prop_actors(world)
            # Sprint 14: prop actors are split per streaming cell ("<label> cX_Y")
            for prefix in BLOCKING:
                group = [a for lbl, a in actors.items() if lbl == prefix or lbl.startswith(prefix + " c")]
                if not group:
                    raise RuntimeError(f"missing prop actor {prefix}")
                if not all(a.blocks_movement() for a in group):
                    raise RuntimeError(f"{prefix} does not block movement")
            for prefix in WALK_THROUGH:
                if any(a.blocks_movement() for lbl, a in actors.items() if lbl == prefix or lbl.startswith(prefix + " c")):
                    raise RuntimeError(f"{prefix} must stay walk-through")
            # Ground traces (Visibility) must pass through props: trace down onto the first tree trunk.
            tree = next(a for lbl, a in sorted(actors.items()) if lbl.startswith("Altstadt HISM Trees 0"))
            _, t = next(instances(tree))
            hit = unreal.SystemLibrary.line_trace_single(
                world, t.translation + unreal.Vector(0, 0, 250.0), t.translation - unreal.Vector(0, 0, 200.0),
                unreal.TraceTypeQuery.ECC_VISIBILITY, False, [pawn], unreal.DrawDebugTrace.NONE, False,
            )
            if hit is not None and hit.to_dict()["hit_actor"] == tree:
                raise RuntimeError("Visibility trace hit a tree trunk; props must ignore Visibility")
            phase = "pick"
            return
        if phase == "pick":
            if test_index >= len(WALK_TESTS):
                finish("DOEMITZ_PROP_COLLISION_PIE_OK: " + "; ".join(results), True)
                phase = "done"
                return
            prefix, radius_cm, along_y = WALK_TESTS[test_index]
            actors = prop_actors(world)
            current = None
            for label in sorted(actors):
                if label.startswith(prefix) and actors[label].blocks_movement():
                    current = pick_candidate(world, pawn, actors[label], radius_cm, along_y)
                    if current is not None:
                        current["label"] = label
                        break
            if current is None:
                raise RuntimeError(f"no free-standing instance found for {prefix}")
            pawn.set_actor_location(current["start"], False, True)
            current["min"] = None
            walk_start = monotonic()
            phase = "walk"
            return
        if phase != "walk":
            return
        pos = pawn.get_actor_location()
        c = current["center"]
        dist = hypot(pos.x - c.x, pos.y - c.y)
        current["min"] = dist if current["min"] is None else min(current["min"], dist)
        if monotonic() - walk_start < 0.4:
            return  # land after the teleport
        if monotonic() - walk_start < WALK_SECONDS + 0.4:
            d = unreal.Vector(c.x - pos.x, c.y - pos.y, 0.0)
            if d.length() > 1.0:
                pawn.add_movement_input(d / d.length(), 1.0, False)
            return
        unreal.log(f"DOEMITZ_PROP_COLLISION_DEBUG: {current['label']} start={current['start']} center={c} end={pos} "
                   f"min={current['min']:.0f} vel={pawn.get_velocity()} mode="
                   f"{pawn.get_editor_property('character_movement').get_editor_property('movement_mode')}")
        lo = current["expected"] - 10.0
        hi = current["expected"] + 35.0
        if current["min"] < lo:
            raise RuntimeError(
                f"{current['label']}: player walked into the prop ({current['min']:.0f} cm < {lo:.0f} cm)")
        if current["min"] > hi:
            raise RuntimeError(
                f"{current['label']}: player stopped too early ({current['min']:.0f} cm > {hi:.0f} cm)")
        results.append(f"{current['label']} stopped at {current['min']:.0f} cm (expected {current['expected']:.0f})")
        test_index += 1
        phase = "pick"
    except Exception:
        phase = "done"
        finish("DOEMITZ_PROP_COLLISION_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(tick)
level.editor_request_begin_play()
