from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
sim_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzSimulationSubsystem")
citizen_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzCitizenActor")
deadline = monotonic() + 120
phase = "init"
anna_actor = None
anna_moved = False
bernd_destroyed = False
bernd_moved_headless = False


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def check(_delta_seconds):
    global phase, anna_actor, anna_moved, bernd_destroyed, bernd_moved_headless
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
            if count != 4:
                raise RuntimeError(f"expected 4 simulated citizens, got {count}")
            actors = unreal.GameplayStatics.get_all_actors_of_class(world, citizen_class)
            if len(actors) != 4:
                raise RuntimeError(f"expected 4 citizen actors, got {len(actors)}")
            by_id = {}
            for actor in actors:
                mesh_comp = actor.get_editor_property("citizen_mesh")
                if mesh_comp.get_editor_property("static_mesh") is None:
                    raise RuntimeError(f"citizen actor {actor.get_name()} has no mesh")
                by_id[str(actor.get_citizen_id())] = actor
            if "citizen_anna_01" not in by_id or "citizen_bernd_02" not in by_id:
                raise RuntimeError(f"missing expected citizen IDs: {sorted(by_id)}")
            anna_actor = by_id["citizen_anna_01"]
            # Destroy Bernd's 3D actor to prove simulation state continues without representation.
            by_id["citizen_bernd_02"].destroy_actor()
            bernd_destroyed = True
            # Trigger Anna's 07:55 commute and Bernd's 08:00 commute quickly.
            sub.set_time_of_day_minutes(475.0)
            sub.set_time_scale(300.0)
            unreal.GameplayStatics.set_global_time_dilation(world, 8.0)
            phase = "simulate"
            return

        if phase == "simulate":
            res_anna = sub.get_citizen_state("citizen_anna_01")
            res_bernd = sub.get_citizen_state("citizen_bernd_02")
            anna = res_anna[1] if isinstance(res_anna, tuple) else res_anna
            bernd = res_bernd[1] if isinstance(res_bernd, tuple) else res_bernd
            if anna is None or bernd is None:
                raise RuntimeError("failed to query citizen states")

            if anna.get_editor_property("is_moving"):
                anna_moved = True
                sim_loc = anna.get_editor_property("world_location")
                actor_loc = anna_actor.get_actor_location()
                if (sim_loc - actor_loc).length() > 50.0:
                    raise RuntimeError("citizen actor diverged from simulation state")

            if bernd.get_editor_property("is_moving"):
                bernd_moved_headless = True

            anna_done = (
                anna_moved
                and anna.get_editor_property("completed_trips") >= 1
                and str(anna.get_editor_property("current_place_id")) == "place_amtsverwaltung"
            )
            bernd_done = (
                bernd_destroyed
                and bernd_moved_headless
                and bernd.get_editor_property("completed_trips") >= 1
                and str(bernd.get_editor_property("current_place_id")) == "place_kaufhaus"
            )

            if anna_done and bernd_done:
                finish(
                    f"DOEMITZ_CITIZENS_PIE_OK: 4 citizens active, Anna commuted with 3D actor to place_amtsverwaltung, "
                    f"Bernd completed headless commute without 3D actor to place_kaufhaus",
                    True,
                )
    except Exception:
        finish("DOEMITZ_CITIZENS_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
