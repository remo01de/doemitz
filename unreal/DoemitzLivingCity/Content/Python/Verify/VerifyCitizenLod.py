from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
deadline = monotonic() + 90
phase = "setup"
coarse_start_loc = None
coarse_ticks = 0


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def get_state(sub, cid):
    res = sub.get_citizen_state(cid)
    return res[1] if isinstance(res, tuple) else res


def check(_delta_seconds):
    global phase, coarse_start_loc, coarse_ticks
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during {phase}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        cit = unreal.DoemitzCitizenSubsystem.get(world)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if sub is None or cit is None or cit.get_citizen_count() < 30 or pawn is None:
            return

        if phase == "setup":
            # Start Anna's morning commute and move player far away (> 150 m) so Anna enters coarse LOD (no actor)
            sub.set_time_of_day_minutes(475.0)
            sub.set_time_scale(sub.get_base_time_scale())
            unreal.GameplayStatics.set_global_time_dilation(world, 4.0)
            anna = get_state(cit, "citizen_anna_01")
            anna_loc = anna.get_editor_property("world_location")
            pawn.set_actor_location(anna_loc + unreal.Vector(40000.0, 40000.0, 200.0), False, True)
            coarse_start_loc = anna_loc
            coarse_ticks = 0
            phase = "verify_far_coarse"
            return

        if phase == "verify_far_coarse":
            coarse_ticks += 1
            if cit.is_citizen_high_detail("citizen_anna_01"):
                if coarse_ticks > 30:
                    raise RuntimeError("Anna stayed high detail even though player is > 150 m away")
                return
            actor_loc_far = cit.get_citizen_actor_location("citizen_anna_01")
            if actor_loc_far is not None:
                raise RuntimeError("Anna still has an active actor outside 150 m LOD radius")

            anna = get_state(cit, "citizen_anna_01")
            anna_loc = anna.get_editor_property("world_location")
            if (anna_loc - coarse_start_loc).length() < 150.0:
                return

            # Anna moved in coarse 1 Hz mode without an actor; now teleport player right beside her (< 150 m)
            pawn.set_actor_location(anna_loc + unreal.Vector(300.0, 0.0, 100.0), False, True)
            phase = "verify_reenter"
            return

        if phase == "verify_reenter":
            if not cit.is_citizen_high_detail("citizen_anna_01"):
                return
            actor_loc = cit.get_citizen_actor_location("citizen_anna_01")
            if actor_loc is None:
                raise RuntimeError("Anna re-entered 150 m radius but did not receive a pooled actor")
            anna = get_state(cit, "citizen_anna_01")
            sim_loc = anna.get_editor_property("world_location")
            delta_cm = (actor_loc - sim_loc).length()
            if delta_cm > 25.0:
                raise RuntimeError(f"Re-entered citizen actor position mismatch: {delta_cm:.1f} cm")

            finish(
                f"DOEMITZ_CITIZEN_LOD_PIE_OK: 30 citizens, Anna exited 150m radius (actor released, coarse moved "
                f"{(sim_loc - coarse_start_loc).length():.1f} cm) and re-entered with pooled actor match delta={delta_cm:.2f} cm "
                f"(active={cit.get_active_citizen_actor_count()}, pooled={cit.get_pooled_citizen_actor_count()})",
                True,
            )
            phase = "done"
    except Exception:
        phase = "done"
        finish("DOEMITZ_CITIZEN_LOD_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
