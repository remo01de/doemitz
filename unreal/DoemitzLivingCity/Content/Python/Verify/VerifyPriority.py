from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
deadline = monotonic() + 90

# Real Altstadt junction osm:node:36552454 (An der Bleiche meets Torstrasse):
# - An der Bleiche (edge:osm:way:157877525:0:0:fwd, len=212.37 m) has OSM highway=give_way AND comes from Torstrasse's RIGHT!
# - Torstrasse (edge:osm:way:178018735:0:1:rev, len=30.60 m) has NO yield sign (priority road B 195).
# Under Rechts vor links, An der Bleiche would have had priority; give_way MUST override it so An der Bleiche yields!
PRIO_NODE = "osm:node:36552454"
GIVE_WAY_EDGE = "edge:osm:way:157877525:0:0:fwd"
GIVE_WAY_DIST_CM = 20600.0   # ~6.4 m before junction
MAIN_EDGE = "edge:osm:way:178018735:0:1:rev"
MAIN_DIST_CM = 2420.0        # ~6.4 m before junction

phase = "setup_give_way"
ticks = 0


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def get_vstate(sub, vid):
    res = sub.get_vehicle_state(vid)
    return res[1] if isinstance(res, tuple) else res


def check(_delta_seconds):
    global phase, ticks
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during {phase}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        if sub is None or sub.get_vehicle_count() < 8:
            return

        if phase == "setup_give_way":
            gw_rule = sub.get_edge_yield_rule(GIVE_WAY_EDGE)
            main_rule = sub.get_edge_yield_rule(MAIN_EDGE)
            if gw_rule != unreal.DoemitzYieldRule.GIVE_WAY:
                raise RuntimeError(f"expected GIVE_WAY on {GIVE_WAY_EDGE}, got {gw_rule}")
            if main_rule != unreal.DoemitzYieldRule.NONE:
                raise RuntimeError(f"expected NONE on {MAIN_EDGE}, got {main_rule}")

            unreal.GameplayStatics.set_global_time_dilation(world, 1.0)
            if not sub.set_vehicle_edge_position_for_test("altstadt_vehicle_01", GIVE_WAY_EDGE, GIVE_WAY_DIST_CM, 300.0):
                raise RuntimeError("failed to place vehicle_01 on give_way edge")
            if not sub.set_vehicle_edge_position_for_test("altstadt_vehicle_02", MAIN_EDGE, MAIN_DIST_CM, 300.0):
                raise RuntimeError("failed to place vehicle_02 on main road edge")
            ticks = 0
            phase = "verify_give_way"
            return

        if phase == "verify_give_way":
            ticks += 1
            st_gw = get_vstate(sub, "altstadt_vehicle_01")
            holder = str(sub.get_junction_reservation(PRIO_NODE))
            gw_yielding = bool(st_gw.get_editor_property("yielding_for_priority_sign"))
            if gw_yielding and holder == "altstadt_vehicle_02":
                # Now also verify STOP sign forces a full stop even with no opposing vehicle
                sub.set_edge_yield_rule_for_test(GIVE_WAY_EDGE, unreal.DoemitzYieldRule.STOP)
                sub.set_vehicle_edge_position_for_test("altstadt_vehicle_01", GIVE_WAY_EDGE, GIVE_WAY_DIST_CM, 350.0)
                sub.set_vehicle_edge_position_for_test("altstadt_vehicle_02", "edge:osm:way:104838487:0:0:fwd", 1000.0, 200.0)
                ticks = 0
                phase = "verify_stop_sign"
                return
            if ticks > 40:
                raise RuntimeError(
                    f"give_way override not observed after {ticks} ticks: holder={holder}, gw_yielding={gw_yielding}"
                )

        if phase == "verify_stop_sign":
            ticks += 1
            st_stop = get_vstate(sub, "altstadt_vehicle_01")
            stopping = bool(st_stop.get_editor_property("stopping_for_stop_sign"))
            speed = float(st_stop.get_editor_property("current_speed_cm_per_second"))
            if stopping and speed <= 15.0:
                # Restore original rule cleanly
                sub.set_edge_yield_rule_for_test(GIVE_WAY_EDGE, unreal.DoemitzYieldRule.GIVE_WAY)
                finish(
                    f"DOEMITZ_PRIORITY_PIE_OK: give_way at {PRIO_NODE} ({GIVE_WAY_EDGE}) yielded to {MAIN_EDGE} "
                    f"despite approaching from right; stop sign forced complete halt (speed={speed:.1f} cm/s)",
                    True,
                )
                phase = "done"
                return
            if ticks > 80:
                raise RuntimeError(f"stop sign halt not observed after {ticks} ticks: stopping={stopping}, speed={speed:.1f}")
    except Exception:
        phase = "done"
        finish("DOEMITZ_PRIORITY_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
