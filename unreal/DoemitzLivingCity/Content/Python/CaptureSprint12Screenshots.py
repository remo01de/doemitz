"""Capture fixed-camera Sprint 12 visual verification screenshots into Saved/Screenshots/Sprint12/."""

from math import atan2, degrees, hypot
from pathlib import Path
from time import monotonic
import traceback

import unreal


OUT_DIR = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())) / "Screenshots" / "Sprint12"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def ue_pos(east_m, north_m, z_m):
    return unreal.Vector(north_m * 100.0, east_m * 100.0, z_m * 100.0)


def look_at_rot(cam: unreal.Vector, target: unreal.Vector) -> unreal.Rotator:
    dx = target.x - cam.x
    dy = target.y - cam.y
    dz = target.z - cam.z
    horiz = max(hypot(dx, dy), 1.0)
    yaw = degrees(atan2(dy, dx))
    pitch = degrees(atan2(dz, horiz))
    return unreal.Rotator(pitch=pitch, yaw=yaw, roll=0.0)


SHOTS = [
    ("01_johanneskirche.png", ue_pos(8.0, -64.0, 22.0), ue_pos(38.0, -96.0, 21.0)),
    ("02_rathaus.png", ue_pos(-74.0, -194.0, 9.5), ue_pos(-65.5, -220.0, 11.2)),
    ("03_festung.png", ue_pos(-212.0, -32.0, 26.0), ue_pos(-176.0, -24.0, 8.0)),
    ("04_torbruecke.png", ue_pos(76.0, -25.0, 6.5), ue_pos(50.5, -14.3, 3.2)),
    ("05_steinbruecke.png", ue_pos(-74.0, 141.0, 5.8), ue_pos(-95.7, 144.4, 3.0)),
    ("06_nw_steg_tunnelportal.png", ue_pos(-266.0, 44.0, 6.2), ue_pos(-246.0, 22.5, 4.8)),
]

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
deadline = monotonic() + 180
shot_idx = 0
state = "warmup"
wait_ticks = 0
captured = []
current_task = None


def finish(msg, ok):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if ok else unreal.log_error)(msg)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.quit_editor()


def tick(_dt):
    global shot_idx, state, wait_ticks, current_task
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"Screenshot capture timed out at shot {shot_idx} ({state})")

        if state == "warmup":
            wait_ticks += 1
            if wait_ticks < 25:
                return
            level.editor_set_game_view(True)
            world = editor.get_editor_world()
            if world is not None:
                # Match DoemitzLow game lighting (no Lumen MeshSDF black-card artifacts on generated StaticMeshes)
                unreal.SystemLibrary.execute_console_command(world, "r.DynamicGlobalIlluminationMethod 0")
                unreal.SystemLibrary.execute_console_command(world, "r.ReflectionMethod 0")
            state = "position"
            wait_ticks = 0
            return

        if state == "position":
            name, loc, target = SHOTS[shot_idx]
            rot = look_at_rot(loc, target)
            editor.set_level_viewport_camera_info(loc, rot)
            wait_ticks = 0
            state = "settle"
            return

        if state == "settle":
            wait_ticks += 1
            if wait_ticks < 15:
                return
            out_path = str(OUT_DIR / SHOTS[shot_idx][0])
            current_task = unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, out_path, None, False, False)
            wait_ticks = 0
            state = "wait_shot"
            return

        if state == "wait_shot":
            wait_ticks += 1
            out_file = OUT_DIR / SHOTS[shot_idx][0]
            done = (current_task is not None and current_task.is_task_done()) or (out_file.is_file() and out_file.stat().st_size > 1000 and wait_ticks >= 10)
            if not done:
                return
            captured.append(str(out_file))
            shot_idx += 1
            if shot_idx >= len(SHOTS):
                state = "closing"
                wait_ticks = 0
                return
            state = "position"
            return

        if state == "closing":
            wait_ticks += 1
            if wait_ticks >= 10:
                finish(f"DOEMITZ_SPRINT12_SCREENSHOTS_OK: {len(captured)}/{len(SHOTS)} saved to {OUT_DIR}", True)
    except Exception:
        finish("DOEMITZ_SPRINT12_SCREENSHOTS_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(tick)
