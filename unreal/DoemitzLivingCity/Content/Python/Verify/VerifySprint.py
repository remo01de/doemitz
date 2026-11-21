import time
import traceback

import unreal


level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
subsystems = unreal.get_default_object(unreal.load_class(None, "/Script/Engine.SubsystemBlueprintLibrary"))
action = unreal.load_asset("/Game/Input/Actions/IA_Sprint")
native_character = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzCharacter")
if not (action and native_character):
    raise RuntimeError("Sprint action or native character is missing")
if "DoemitzAltstadt" not in editor.get_editor_world().get_path_name():
    raise RuntimeError("DoemitzAltstadt was not loaded")

pressed = unreal.Vector(1.0, 0.0, 0.0)
released = unreal.Vector(0.0, 0.0, 0.0)
deadline = time.monotonic() + 180
walk_speed = None
sprint_observed = False


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def verify_tick(_delta_seconds):
    global walk_speed, sprint_observed
    try:
        if time.monotonic() > deadline:
            finish("DOEMITZ_SPRINT_PIE_FAILED: test timed out", False)
            return
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        controller = unreal.GameplayStatics.get_player_controller(world, 0)
        if controller is None:
            return
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if pawn is None:
            return
        if pawn.get_editor_property("sprint_action") != action:
            raise RuntimeError("The active pawn does not use IA_Sprint")

        movement = pawn.get_editor_property("character_movement")
        inputs = subsystems.call_method(
            "GetLocalPlayerSubSystemFromPlayerController",
            (controller, unreal.EnhancedInputLocalPlayerSubsystem.static_class()),
        )
        keys = {key.export_text() for key in inputs.query_keys_mapped_to_action(action)}
        if "LeftShift" not in keys:
            return

        speed = movement.get_editor_property("max_walk_speed")
        sprint_speed = pawn.get_editor_property("sprint_speed")
        if walk_speed is None:
            walk_speed = speed
            if walk_speed >= sprint_speed:
                raise RuntimeError(f"Expected sprint speed above walking speed, got {walk_speed} and {sprint_speed}")
        if not sprint_observed:
            if abs(speed - sprint_speed) < 0.1:
                sprint_observed = True
            else:
                inputs.inject_input_vector_for_action(action, pressed, [], [])
                return
        if abs(speed - walk_speed) < 0.1:
            finish(f"DOEMITZ_SPRINT_PIE_OK: {walk_speed} -> {sprint_speed} -> {speed} cm/s", True)
        else:
            inputs.inject_input_vector_for_action(action, released, [], [])
    except Exception:
        finish("DOEMITZ_SPRINT_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(verify_tick)
level.editor_request_begin_play()
