from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
deadline = monotonic() + 120
phase = "init"
anna_moved = False
bernd_moved = False


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def get_state(sub, cid):
    res = sub.get_citizen_state(cid)
    return res[1] if isinstance(res, tuple) else res


def check(_delta_seconds):
    global phase, anna_moved, bernd_moved
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during {phase}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        if sub is None or sub.get_citizen_count() == 0:
            return

        if phase == "init":
            count = sub.get_citizen_count()
            if count < 30:
                raise RuntimeError(f"expected at least 30 simulated citizens, got {count}")
            ids = {str(cid) for cid in sub.get_all_citizen_ids()}
            for legacy in ("citizen_anna_01", "citizen_bernd_02", "citizen_clara_03", "citizen_dieter_04"):
                if legacy not in ids:
                    raise RuntimeError(f"missing legacy citizen {legacy}")
            # Trigger Anna's 07:55 commute and Bernd's 08:00 commute quickly.
            sub.set_time_of_day_minutes(475.0)
            sub.set_time_scale(300.0)
            unreal.GameplayStatics.set_global_time_dilation(world, 8.0)
            phase = "simulate"
            return

        if phase == "simulate":
            anna = get_state(sub, "citizen_anna_01")
            bernd = get_state(sub, "citizen_bernd_02")
            if anna is None or bernd is None:
                raise RuntimeError("failed to query citizen states")

            if anna.get_editor_property("is_moving"):
                anna_moved = True
                actor_loc = sub.get_citizen_actor_location("citizen_anna_01")
                if actor_loc is not None:
                    sim_loc = anna.get_editor_property("world_location")
                    if (sim_loc - actor_loc).length() > 50.0:
                        raise RuntimeError("citizen actor diverged from simulation state")

            if bernd.get_editor_property("is_moving"):
                bernd_moved = True

            anna_done = (
                anna_moved
                and anna.get_editor_property("completed_trips") >= 1
                and str(anna.get_editor_property("current_place_id")) == "place_amtsverwaltung"
            )
            bernd_done = (
                bernd_moved
                and bernd.get_editor_property("completed_trips") >= 1
                and str(bernd.get_editor_property("current_place_id")) == "place_kaufhaus"
            )

            if anna_done and bernd_done:
                finish(
                    f"DOEMITZ_CITIZENS_PIE_OK: {sub.get_citizen_count()} citizens simulated, "
                    f"Anna commuted to place_amtsverwaltung, Bernd commuted to place_kaufhaus "
                    f"(active actors={sub.get_active_citizen_actor_count()})",
                    True,
                )
    except Exception:
        finish("DOEMITZ_CITIZENS_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
