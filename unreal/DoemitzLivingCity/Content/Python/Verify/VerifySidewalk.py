import json
from pathlib import Path
from time import monotonic
import traceback

import unreal

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
source = project.parents[1] / "data/processed/doemitz-altstadt/unreal-city-meshes.json"
package = json.loads(source.read_text(encoding="utf-8"))
east, north, height = package["sidewalk_probe_m"]
sidewalk = unreal.Vector(north * 100, east * 100, 0)
deadline = monotonic() + 95
start = None
on_sidewalk = False


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def walk(_delta_seconds):
    global start, on_sidewalk
    try:
        if monotonic() > deadline:
            finish(f"DOEMITZ_SIDEWALK_PIE_FAILED: timeout, reached sidewalk={on_sidewalk}", False)
            return
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if pawn is None or not pawn.get_editor_property("character_movement").is_moving_on_ground():
            return
        position = pawn.get_actor_location()
        if start is None:
            start = position
        destination = start if on_sidewalk else sidewalk
        direction = unreal.Vector(destination.x - position.x, destination.y - position.y, 0)
        distance = direction.length()
        if distance > 12:
            pawn.add_movement_input(direction / distance, min(0.55, distance / 100), False)
            return
        if not on_sidewalk:
            rise = position.z - start.z
            if abs(rise - height * 100) > 4:
                raise RuntimeError(f"Unexpected curb rise of {rise:.1f} cm")
            on_sidewalk = True
            return
        drop = abs(position.z - start.z)
        if drop <= 4:
            walked = unreal.Vector(sidewalk.x - start.x, sidewalk.y - start.y, 0).length()
            finish(f"DOEMITZ_SIDEWALK_PIE_OK: crossed {walked:.1f} cm onto sidewalk and returned", True)
    except Exception:
        finish("DOEMITZ_SIDEWALK_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(walk)
level.editor_request_begin_play()
