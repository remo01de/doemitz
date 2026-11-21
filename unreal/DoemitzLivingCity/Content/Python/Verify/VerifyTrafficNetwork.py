from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
vehicle_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzTrafficVehicle")

EXPECTED_IDS = [f"altstadt_vehicle_0{i}" for i in range(1, 6)]
# Real 90-degree Altstadt junction (Fritz-Reuter-Strasse / Goethestrasse):
# Edge A approaches from left and must yield to Edge B approaching from the right (dot = 1.0).
RVL_NODE = "osm:node:277309010"
RVL_LEFT_EDGE = "edge:osm:way:157877527:0:0:fwd"
RVL_LEFT_DIST_CM = 4650.0   # ~6.2 m before junction (length 52.7 m)
RVL_RIGHT_EDGE = "edge:osm:way:25642325:0:1:fwd"
RVL_RIGHT_DIST_CM = 2900.0  # ~6.4 m before junction (length 35.4 m)

deadline = monotonic() + 120
phase = "drive_network"
min_pair_dist_cm = 1e9
rvl_ticks = 0
rvl_verified = False


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def get_vstate(sub, vid):
    res = sub.get_vehicle_state(vid)
    return res[1] if isinstance(res, tuple) else res


def check(_delta_seconds):
    global phase, min_pair_dist_cm, rvl_ticks, rvl_verified
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during {phase}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        if sub is None or sub.get_vehicle_count() == 0:
            return
        actors = unreal.GameplayStatics.get_all_actors_of_class(world, vehicle_class)
        if len(actors) != 5:
            details = [(a.get_name(), str(a.get_vehicle_id())) for a in actors]
            raise RuntimeError(f"expected 5 traffic vehicle actors, found {len(actors)}: {details}")

        if phase == "drive_network":
            unreal.GameplayStatics.set_global_time_dilation(world, 8.0)
            states = {}
            for vid in EXPECTED_IDS:
                st = get_vstate(sub, vid)
                states[vid] = st

            # Check pairwise 2D distance (no overlap / penetration)
            locs = [states[vid].get_editor_property("world_location") for vid in EXPECTED_IDS]
            for i in range(len(locs)):
                for j in range(i + 1, len(locs)):
                    dx = locs[i].x - locs[j].x
                    dy = locs[i].y - locs[j].y
                    d = (dx * dx + dy * dy) ** 0.5
                    if d < min_pair_dist_cm:
                        min_pair_dist_cm = d
                    if d < 220.0:
                        raise RuntimeError(
                            f"vehicle overlap detected between {EXPECTED_IDS[i]} and {EXPECTED_IDS[j]}: {d:.1f} cm"
                        )

            decisions = [states[vid].get_editor_property("junction_decisions") for vid in EXPECTED_IDS]
            if all(d >= 3 for d in decisions):
                # Move to Right-before-Left (Rechts vor links) deterministic scenario
                unreal.GameplayStatics.set_global_time_dilation(world, 1.0)
                if not sub.set_vehicle_edge_position_for_test("altstadt_vehicle_01", RVL_LEFT_EDGE, RVL_LEFT_DIST_CM, 300.0):
                    raise RuntimeError("failed to position vehicle_01 for right-before-left test")
                if not sub.set_vehicle_edge_position_for_test("altstadt_vehicle_02", RVL_RIGHT_EDGE, RVL_RIGHT_DIST_CM, 300.0):
                    raise RuntimeError("failed to position vehicle_02 for right-before-left test")
                phase = "verify_rvl"
                rvl_ticks = 0
            return

        if phase == "verify_rvl":
            rvl_ticks += 1
            st_left = get_vstate(sub, "altstadt_vehicle_01")
            st_right = get_vstate(sub, "altstadt_vehicle_02")
            holder = str(sub.get_junction_reservation(RVL_NODE))
            left_yielding = bool(st_left.get_editor_property("yielding_for_right_of_way"))
            if left_yielding and holder == "altstadt_vehicle_02":
                rvl_verified = True
                decisions_summary = {
                    vid: get_vstate(sub, vid).get_editor_property("junction_decisions")
                    for vid in EXPECTED_IDS
                }
                finish(
                    f"DOEMITZ_TRAFFIC_NETWORK_PIE_OK: 5 vehicles, decisions={decisions_summary}, "
                    f"min_pair_dist={min_pair_dist_cm:.1f} cm, rvl_node={RVL_NODE} holder={holder} left_yielded=True",
                    True,
                )
                phase = "done"
                return
            if rvl_ticks > 40:
                raise RuntimeError(
                    f"right-before-left not observed after {rvl_ticks} ticks: "
                    f"holder={holder}, left_yielding={left_yielding}, "
                    f"right_yielding={st_right.get_editor_property('yielding_for_right_of_way')}"
                )
    except Exception:
        phase = "done"
        finish("DOEMITZ_TRAFFIC_NETWORK_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
