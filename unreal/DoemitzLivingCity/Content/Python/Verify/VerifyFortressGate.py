"""Sprint 13 PIE check: the player walks from "An der Festung" over the moat bridges, through the gate passage
(osm:way:120431987) and into the fortress courtyard without getting stuck or leaving the passage floor."""

import json
from math import hypot
from pathlib import Path
from time import monotonic
import traceback

import unreal

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
package = json.loads((project.parents[1] / "data/processed/doemitz-altstadt/unreal-city-meshes.json").read_text(encoding="utf-8"))
gate = next(p for p in package["tunnel_portals"] if p["road_id"] == "osm:way:120431987")
bridge = next(b for b in package["bridges"] if b["id"] == "bridge:osm:way:120431984")

# Local metres (east, north). OSM vertices of the moat bridges osm:way:120431986/-984 and the approach
# osm:way:416256368; the passage polyline comes from the package (courtyard end first, gate end last).
south_abutment = next(a for a in bridge["abutments"] if a["position_m"][1] < -100.0)["position_m"]
route_m = [
    south_abutment[:2],
    [-175.9, -93.4],
    [-170.7, -86.9],
    [-168.46, -84.57],
] + [p[:2] for p in reversed(gate["polyline_3d_m"])] + [[-163.2, -48.0]]
passage = gate["polyline_3d_m"]
CAPSULE_HALF_H = 90.0


def ue(p):
    return unreal.Vector(p[1] * 100.0, p[0] * 100.0, (p[2] if len(p) > 2 else 0.0) * 100.0)


def passage_floor_cm(x_cm, y_cm):
    """Floor height (cm) of the nearest passage segment, or None if more than 1.5 m away from the axis."""
    best = None
    for a, b in zip(passage, passage[1:]):
        ax, ay, az = a[1] * 100.0, a[0] * 100.0, a[2] * 100.0
        bx, by, bz = b[1] * 100.0, b[0] * 100.0, b[2] * 100.0
        dx, dy = bx - ax, by - ay
        ll = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((x_cm - ax) * dx + (y_cm - ay) * dy) / max(ll, 1.0)))
        d = hypot(x_cm - (ax + t * dx), y_cm - (ay + t * dy))
        if best is None or d < best[0]:
            best = (d, az + t * (bz - az))
    return best[1] if best and best[0] <= 150.0 else None


deadline = monotonic() + 120
phase = "init"
wp = 1
walk_start = 0.0
max_dev = 0.0
min_feet = None
inside_samples = 0


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def tick(_dt):
    global phase, wp, walk_start, max_dev, min_feet, inside_samples
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out in phase {phase} at waypoint {wp}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0) if world else None
        if pawn is None:
            return
        if phase == "init":
            start = ue(south_abutment)
            pawn.set_actor_location(start + unreal.Vector(0, 0, CAPSULE_HALF_H + 30.0), False, True)
            walk_start = monotonic()
            phase = "walk"
            return
        if phase != "walk":
            return
        pos = pawn.get_actor_location()
        feet = pos.z - CAPSULE_HALF_H
        min_feet = feet if min_feet is None else min(min_feet, feet)
        if pawn.get_editor_property("character_movement").is_moving_on_ground():
            floor_cm = passage_floor_cm(pos.x, pos.y)
            if floor_cm is not None:
                inside_samples += 1
                dev = abs(feet - (floor_cm + 8.0))  # road surface sits 8 cm above the profile
                max_dev = max(max_dev, dev)
                if dev > 12.0:
                    raise RuntimeError(f"player left the passage floor by {dev:.1f} cm at ({pos.x:.0f},{pos.y:.0f})")
        if monotonic() - walk_start > 60.0:
            raise RuntimeError(f"player stuck before waypoint {wp} at {pos}")
        target = ue(route_m[wp])
        d = unreal.Vector(target.x - pos.x, target.y - pos.y, 0.0)
        if d.length() < 60.0:
            wp += 1
            if wp >= len(route_m):
                if inside_samples < 20:
                    raise RuntimeError(f"only {inside_samples} samples inside the passage")
                courtyard_floor = gate["entry_point_3d_m"][2] * 100.0
                if feet < courtyard_floor - 60.0:
                    raise RuntimeError(f"player ended below the courtyard: feet {feet:.0f} vs {courtyard_floor:.0f}")
                phase = "done"
                finish(
                    f"DOEMITZ_FORTRESS_GATE_PIE_OK: walked bridges -> gate passage -> courtyard in "
                    f"{monotonic() - walk_start:.1f}s, passage samples={inside_samples}, max floor dev={max_dev:.1f}cm, "
                    f"lowest feet={min_feet / 100.0:.2f}m local",
                    True,
                )
            return
        pawn.add_movement_input(d / d.length(), 1.0, False)
    except Exception:
        phase = "done"
        finish("DOEMITZ_FORTRESS_GATE_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(tick)
level.editor_request_begin_play()
