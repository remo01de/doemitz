from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
cfg_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzSimulationConfig")
APOTHEKE_ID = "poi:osm:node:1794647095"
deadline = monotonic() + 90
done = False


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def check(_delta_seconds):
    global done
    try:
        if done:
            return
        if monotonic() > deadline:
            raise RuntimeError("timed out waiting for interaction test")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        cfgs = unreal.GameplayStatics.get_all_actors_of_class(world, cfg_class)
        if sub is None or sub.get_citizen_count() == 0 or pawn is None or len(cfgs) != 1:
            return
        widget = cfgs[0].get_clock_widget()
        if widget is None:
            return
        interaction = pawn.get_interaction_component()
        if interaction is None:
            raise RuntimeError("player pawn has no DoemitzInteractionComponent")

        place = sub.get_place_definition(APOTHEKE_ID)
        if place is None:
            raise RuntimeError(f"place {APOTHEKE_ID} not found")
        ent_loc = place.get_editor_property("entrance_location")
        ent_id = str(place.get_editor_property("entrance_id"))
        if ent_id != f"entrance:{APOTHEKE_ID}":
            raise RuntimeError(f"unexpected entrance_id: {ent_id}")

        # Sprint 13: the Apotheke has a walk-in interior; while open the menu waits at the counter inside
        counter_loc = sub.get_place_interaction_location(APOTHEKE_ID)
        if (counter_loc - ent_loc).length() < 150.0:
            raise RuntimeError("expected the Apotheke interaction point at the counter inside, not at the street door")
        pawn.set_actor_location(counter_loc + unreal.Vector(20.0, 0.0, 92.0), False, True)

        # 1. Monday 10:00 (open until 12:30)
        sub.set_day_number(1)
        sub.set_time_of_day_minutes(600.0)
        interaction.refresh_nearest_entrance()
        widget.refresh_display()

        if not interaction.has_interactable_entrance():
            raise RuntimeError("expected interactable entrance within 2 m of Apotheke")
        if str(interaction.get_nearest_place_id()) != APOTHEKE_ID:
            raise RuntimeError(f"expected nearest place {APOTHEKE_ID}, got {interaction.get_nearest_place_id()}")
        if not interaction.is_nearest_place_open():
            raise RuntimeError("expected Apotheke to be open on Monday 10:00")
        open_status = sub.get_place_opening_status(APOTHEKE_ID)
        if not open_status.get_editor_property("open") or open_status.get_editor_property("next_change_minute") != 750:
            raise RuntimeError(f"unexpected open status struct: {open_status}")
        open_prompt = interaction.get_interaction_prompt()
        hud_prompt = widget.get_interaction_prompt_string()
        if "Fritz-Reuter-Apotheke" not in open_prompt or "ge\u00f6ffnet bis 12:30" not in open_prompt:
            raise RuntimeError(f"unexpected open prompt: {open_prompt!r}")
        if hud_prompt != open_prompt:
            raise RuntimeError(f"HUD prompt mismatch: {hud_prompt!r} vs {open_prompt!r}")

        if not interaction.try_interact() or not interaction.is_menu_open():
            raise RuntimeError("TryInteract failed to open menu at open Apotheke")
        interaction.close_menu()
        if interaction.is_menu_open():
            raise RuntimeError("CloseMenu failed to close menu")

        # 2. Sunday 10:00 (closed, opens Monday 08:00) -> entry must be rejected at the street door
        pawn.set_actor_location(ent_loc + unreal.Vector(0.0, 0.0, 90.0), False, True)
        sub.set_day_number(7)
        sub.set_time_of_day_minutes(600.0)
        interaction.refresh_nearest_entrance()
        widget.refresh_display()

        if interaction.is_nearest_place_open():
            raise RuntimeError("expected Apotheke to be closed on Sunday 10:00")
        closed_status = sub.get_place_opening_status(APOTHEKE_ID)
        if closed_status.get_editor_property("open") or closed_status.get_editor_property("next_change_weekday") != 0:
            raise RuntimeError(f"unexpected closed status struct: {closed_status}")
        closed_prompt = interaction.get_interaction_prompt()
        if "geschlossen, \u00f6ffnet Mo 08:00" not in closed_prompt:
            raise RuntimeError(f"unexpected closed prompt: {closed_prompt!r}")
        if interaction.try_interact() or interaction.is_menu_open():
            raise RuntimeError("closed Apotheke must not allow entering/opening menu")

        done = True
        finish(
            f"DOEMITZ_INTERACTION_PIE_OK: entrance={ent_id}, open='{open_prompt}' opened/closed menu, "
            f"closed='{closed_prompt}' rejected entry",
            True,
        )
    except Exception:
        done = True
        finish("DOEMITZ_INTERACTION_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
