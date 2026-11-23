"""Sprint 14 PIE check: World Partition streaming of the extended city (Altstadt -> Hafen -> Schleuse).

The runtime grid must use the configured cell size and loading range. The player is moved in 50 m steps from
the Rathaus to the Schleuse Dömitz and on to the harbour; at every step streaming has to complete and a ground
trace below the player has to hit generated ground (terrain, streets, quay, lock coping), so no hole opens
when the player runs into the new area. Finally the player stands on the lock walkway without falling.
"""

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
cells = package["cells"]
lock = package["locks"][0]

# local metres (east, north): Rathaus -> along the Elde to the lock -> harbour promenade
WAYPOINTS = [(-70.0, -220.0), (150.0, -260.0), (400.0, -300.0), (600.0, -300.0), (705.0, -330.0),
             (650.0, -580.0)]
STEP_M = 50.0
deadline = monotonic() + 240
phase = "init"
targets = []
target_idx = 0
wait_start = 0.0
hits = []
max_wait = 0.0
walk_idx = 0
min_walk_feet = None
# across the upper gate: head block A -> heel A -> mitre -> heel B -> head block B
GATE_WALK = [(784.91, -251.76), (783.04, -251.46), (780.2, -248.47), (775.11, -247.71), (773.79, -246.34)]


def ue(e, n, z=0.0):
    return unreal.Vector(n * 100.0, e * 100.0, z * 100.0)


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def ground_hit(world, pawn, x, y):
    hit = unreal.SystemLibrary.line_trace_single(
        world, unreal.Vector(x, y, 6000.0), unreal.Vector(x, y, -3000.0),
        unreal.TraceTypeQuery.ECC_VISIBILITY, False, [pawn], unreal.DrawDebugTrace.NONE, False,
    )
    return hit.to_dict() if hit is not None else None


def tick(_dt):
    global phase, target_idx, wait_start, max_wait, walk_idx, min_walk_feet
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out in phase {phase} at target {target_idx}/{len(targets)}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0) if world else None
        if pawn is None:
            return
        if phase == "init":
            desc = unreal.DoemitzWorldTools.describe_streaming_grid(world)
            unreal.log(f"DOEMITZ_STREAMING_GRID: {desc}")
            want = f"range={int(float(cells['loading_range_m']) * 100)}"
            if want not in desc.replace(".0;", ";"):
                raise RuntimeError(f"runtime grid not configured ({want} expected): {desc}")
            for (ae, an), (be, bn) in zip(WAYPOINTS, WAYPOINTS[1:]):
                d = hypot(be - ae, bn - an)
                n = max(1, int(d // STEP_M))
                for k in range(n):
                    targets.append((ae + (be - ae) * k / n, an + (bn - an) * k / n))
            targets.append(WAYPOINTS[-1])
            phase = "move"
            return
        if phase == "move":
            if target_idx >= len(targets):
                phase = "lock"
                return
            e, n = targets[target_idx]
            pawn.set_actor_location(ue(e, n, 40.0), False, True)
            cm = pawn.get_editor_property("character_movement")
            cm.set_editor_property("gravity_scale", 0.0)
            pawn.get_editor_property("character_movement").stop_movement_immediately()
            wait_start = monotonic()
            phase = "wait"
            return
        if phase == "wait":
            done = unreal.DoemitzWorldTools.is_streaming_completed(world)
            if not done and monotonic() - wait_start < 8.0:
                return
            if not done:
                raise RuntimeError(f"streaming did not complete at {targets[target_idx]}")
            max_wait = max(max_wait, monotonic() - wait_start)
            e, n = targets[target_idx]
            h = ground_hit(world, pawn, n * 100.0, e * 100.0)
            if h is None:
                raise RuntimeError(f"no ground below the player at local ({e:.0f}, {n:.0f}) after streaming")
            hits.append((targets[target_idx], h["hit_actor"].get_actor_label() if h["hit_actor"] else "?"))
            target_idx += 1
            phase = "move"
            return
        if phase == "lock":
            # stand on the upper gate walkway of the lock (middle of the eastern leaf) and let gravity act
            z_walk = float(lock["walkway_z_m"])
            cm = pawn.get_editor_property("character_movement")
            cm.set_editor_property("gravity_scale", 1.0)
            pawn.set_actor_location(ue(781.6, -249.97, z_walk + 1.2), False, True)
            wait_start = monotonic()
            phase = "stand"
            return
        if phase == "stand":
            if monotonic() - wait_start < 2.5:
                return
            z_feet = pawn.get_actor_location().z / 100.0 - 0.9
            z_walk = float(lock["walkway_z_m"])
            if abs(z_feet - z_walk) > 0.35:
                raise RuntimeError(f"player not on the lock walkway: feet {z_feet:.2f} m vs walkway {z_walk:.2f} m")
            e0, n0 = GATE_WALK[0]
            pawn.set_actor_location(ue(e0, n0, z_walk + 1.2), False, True)
            walk_idx = 1
            wait_start = monotonic()
            phase = "gate_walk"
            return
        if phase == "gate_walk":
            pos = pawn.get_actor_location()
            z_feet = pos.z / 100.0 - 0.9
            if monotonic() - wait_start > 1.0:
                min_walk_feet = z_feet if min_walk_feet is None else min(min_walk_feet, z_feet)
            if min_walk_feet is not None and min_walk_feet < float(lock["walkway_z_m"]) - 0.4:
                raise RuntimeError(f"player fell off the gate walkway (feet {min_walk_feet:.2f} m)")
            if monotonic() - wait_start > 20.0:
                raise RuntimeError(f"stuck on the gate walkway before point {walk_idx} at {pos}")
            te, tn = GATE_WALK[walk_idx]
            d = unreal.Vector(tn * 100.0 - pos.x, te * 100.0 - pos.y, 0.0)
            if d.length() < 35.0:
                walk_idx += 1
                if walk_idx >= len(GATE_WALK):
                    labels = sorted({lbl.split("__")[0] for _, lbl in hits})
                    finish(
                        f"DOEMITZ_STREAMING_PIE_OK: {len(hits)} positions Rathaus->Schleuse->Hafen streamed with "
                        f"ground (max wait {max_wait:.1f}s), ground actors {labels[:8]}, crossed the lock on the "
                        f"upper gate walkway (lowest feet {min_walk_feet:.2f} m, walkway {float(lock['walkway_z_m']):.2f} m)",
                        True,
                    )
                    phase = "done"
                return
            pawn.add_movement_input(d / d.length(), 0.6, False)
    except Exception:
        phase = "done"
        finish("DOEMITZ_STREAMING_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(tick)
level.editor_request_begin_play()
