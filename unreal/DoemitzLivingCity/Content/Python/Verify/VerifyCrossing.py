import json
from pathlib import Path
from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
CROSSING_ID = "osm:node:1125976999"
# The edge carrying the zebra crossing comes from the package (edge indices shift when the area grows, Sprint 14)
_project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
_graph = json.loads((_project.parents[1] / "data/processed/doemitz-altstadt/unreal-city-meshes.json")
                    .read_text(encoding="utf-8"))["road-graph"]
_crossing = next(c for c in _graph["crossings"] if c["id"] == CROSSING_ID)
CROSSING_EDGE = next(e for e in _crossing["edge_ids"] if e.endswith(":fwd"))
_edge = next(e for e in _graph["edges"] if e["id"] == CROSSING_EDGE)
_dist_m = next(c["distance_m"] for c in _edge["crossings"] if c["id"] == CROSSING_ID)
APPROACH_DIST_CM = max(0.0, (_dist_m - 6.25) * 100.0)  # ~6.25 m before the zebra crossing

deadline = monotonic() + 90
phase = "setup"
ticks = 0
crossing_loc = None


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def get_vstate(sub, vid):
    res = sub.get_vehicle_state(vid)
    return res[1] if isinstance(res, tuple) else res


def check(_delta_seconds):
    global phase, ticks, crossing_loc
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during {phase}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        if sub is None or sub.get_vehicle_count() == 0 or sub.get_crossing_count() == 0:
            return

        if phase == "setup":
            loc = sub.get_crossing_location(CROSSING_ID)
            if loc is None:
                raise RuntimeError(f"crossing {CROSSING_ID} not found in subsystem")
            crossing_loc = loc
            # Pause citizen schedule movement via test placement right on the zebra crossing
            sub.set_time_scale(60.0)
            unreal.GameplayStatics.set_global_time_dilation(world, 1.0)
            if not sub.set_citizen_position_for_test("citizen_anna_01", crossing_loc):
                raise RuntimeError("failed to place citizen_anna_01 on crossing")
            if not sub.set_vehicle_edge_position_for_test("altstadt_vehicle_01", CROSSING_EDGE, APPROACH_DIST_CM, 400.0):
                raise RuntimeError("failed to place altstadt_vehicle_01 approaching crossing")
            ticks = 0
            phase = "verify_stop"
            return

        if phase == "verify_stop":
            ticks += 1
            sub.set_citizen_position_for_test("citizen_anna_01", crossing_loc)
            st = get_vstate(sub, "altstadt_vehicle_01")
            yielding = bool(st.get_editor_property("yielding_for_crossing"))
            speed = float(st.get_editor_property("current_speed_cm_per_second"))
            if yielding and speed < 50.0:
                # Clear the crossing and confirm the vehicle resumes driving
                sub.set_citizen_position_for_test("citizen_anna_01", crossing_loc + unreal.Vector(2000.0, 2000.0, 0.0))
                ticks = 0
                phase = "verify_resume"
                return
            if ticks > 80:
                raise RuntimeError(
                    f"vehicle did not stop for occupied crossing {CROSSING_ID}: yielding={yielding}, speed={speed:.1f}"
                )
            return

        if phase == "verify_resume":
            ticks += 1
            st = get_vstate(sub, "altstadt_vehicle_01")
            yielding = bool(st.get_editor_property("yielding_for_crossing"))
            speed = float(st.get_editor_property("current_speed_cm_per_second"))
            if not yielding and speed > 100.0:
                finish(
                    f"DOEMITZ_CROSSING_PIE_OK: {sub.get_crossing_count()} crossings loaded, "
                    f"altstadt_vehicle_01 stopped at zebra crossing {CROSSING_ID} for citizen_anna_01 and resumed (speed={speed:.1f} cm/s)",
                    True,
                )
                phase = "done"
                return
            if ticks > 80:
                raise RuntimeError(
                    f"vehicle did not resume after crossing cleared: yielding={yielding}, speed={speed:.1f}"
                )
    except Exception:
        phase = "done"
        finish("DOEMITZ_CROSSING_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
