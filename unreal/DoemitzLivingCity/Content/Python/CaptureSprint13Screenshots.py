"""Capture fixed-camera Sprint 13 visual verification screenshots into Saved/Screenshots/Sprint13/.

Unlike the Sprint 12 capture, the renderer keeps the project defaults (Distance Field AO and Virtual Shadow
Maps on), so the screenshots show whether the generated city meshes are free of distance field artifacts.
Optional: set the environment variable DOEMITZ_SHOTS to a comma-separated list of file stems to capture a subset.
"""

import json
from math import atan2, degrees, hypot
import os
from pathlib import Path
from time import monotonic
import traceback

import unreal


OUT_DIR = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())) / "Screenshots" / "Sprint13"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def ue_pos(east_m, north_m, z_m):
    return unreal.Vector(north_m * 100.0, east_m * 100.0, z_m * 100.0)


def look_at_rot(cam: unreal.Vector, target: unreal.Vector) -> unreal.Rotator:
    dx = target.x - cam.x
    dy = target.y - cam.y
    dz = target.z - cam.z
    horiz = max(hypot(dx, dy), 1.0)
    return unreal.Rotator(pitch=degrees(atan2(dz, horiz)), yaw=degrees(atan2(dy, dx)), roll=0.0)


# (file name, camera (east, north, local z), target (east, north, local z)) in local meters
ALL_SHOTS = [
    ("01_johanneskirche.png", ue_pos(8.0, -64.0, 22.0), ue_pos(38.0, -96.0, 21.0)),
    ("02_rathaus.png", ue_pos(-74.0, -194.0, 9.5), ue_pos(-65.5, -220.0, 11.2)),
    ("03_festung.png", ue_pos(-212.0, -32.0, 26.0), ue_pos(-176.0, -24.0, 8.0)),
    ("04_torbruecke.png", ue_pos(76.0, -25.0, 6.5), ue_pos(50.5, -14.3, 3.2)),
    # In the ditch east of the bridge, looking west along the channel at the vault
    ("05_steinbruecke.png", ue_pos(-76.0, 145.5, 0.8), ue_pos(-96.0, 143.5, 1.4)),
    ("06_nw_steg_tunnelportal.png", ue_pos(-266.0, 44.0, 6.2), ue_pos(-246.0, 22.5, 4.8)),
    ("07_festungstor_aussen.png", ue_pos(-172.4, -90.0, 5.3), ue_pos(-161.5, -79.0, 5.2)),
    ("08_festungstor_durchfahrt.png", ue_pos(-157.1, -74.0, 5.0), ue_pos(-158.6, -56.0, 4.9)),
    ("09_festungstor_hof.png", ue_pos(-164.5, -42.0, 5.4), ue_pos(-158.8, -57.0, 5.0)),
    ("10_wallstrasse_6.png", ue_pos(196.0, -251.0, 7.5), ue_pos(173.2, -240.0, 8.0)),
    ("11_rathausturm.png", ue_pos(-96.0, -212.0, 6.5), ue_pos(-70.0, -231.0, 13.0)),
    # Escarp seen from across the moat (south-west of Bastion Held) and from the drawbridge
    ("21_festungsmauer_bastion_held.png", ue_pos(-262.0, -150.0, 6.0), ue_pos(-240.0, -118.0, 3.0)),
    ("22_festungsmauer_graben.png", ue_pos(-120.0, -110.0, 5.5), ue_pos(-150.0, -80.0, 3.5)),
    # Gorge wall of Bastion Drache from the courtyard, Sandsteintor from the gate forecourt
    ("23_kehlmauer_drache.png", ue_pos(-250.0, -27.0, 9.0), ue_pos(-273.0, -25.0, 9.5)),
    ("24_sandsteintor.png", ue_pos(-167.6, -83.7, 4.9), ue_pos(-162.0, -79.4, 6.0)),
]
# Interior views (day and night), computed from the generated package: camera just inside the door
_project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
_package = json.loads((_project.parents[1] / "data/processed/doemitz-altstadt/unreal-city-meshes.json").read_text(encoding="utf-8"))
_INTERIOR_SLUGS = {"place_kaufhaus": "kaufhaus", "poi:osm:node:1794647095": "apotheke", "poi:osm:way:41020272": "buergerbuero"}
_NIGHT = set()
_idx = 12
for _entry in _package.get("interiors", []):
    _slug = _INTERIOR_SLUGS.get(_entry["place_id"], _entry["id"].split(":")[-1])
    _ins = _entry["door"]["inside_m"]
    _inw = _entry["door"]["inward"]
    _poly = _entry["room_polygon_m"]
    _cx = sum(p[0] for p in _poly) / len(_poly)
    _cy = sum(p[1] for p in _poly) / len(_poly)
    _fz = _entry["floor_z_m"]
    _cam = ue_pos(_ins[0] - _inw[0] * 0.2, _ins[1] - _inw[1] * 0.2, _fz + 1.75)
    _tgt = ue_pos(_cx, _cy, _fz + 1.1)
    ALL_SHOTS.append((f"{_idx:02d}_innen_{_slug}_tag.png", _cam, _tgt))
    ALL_SHOTS.append((f"{_idx + 1:02d}_innen_{_slug}_nacht.png", _cam, _tgt))
    _NIGHT.add(f"{_idx + 1:02d}_innen_{_slug}_nacht.png")
    _idx += 2
    # Exterior view of the opened door from the street
    _out = _entry["door"]["outside_m"]
    ALL_SHOTS.append((f"{_idx:02d}_tuer_{_slug}.png",
                      ue_pos(_out[0] - _inw[0] * 4.5, _out[1] - _inw[1] * 4.5, _out[2] + 1.8),
                      ue_pos(_out[0] + _inw[0] * 1.0, _out[1] + _inw[1] * 1.0, _out[2] + 1.3)))
    _idx += 1

_subset = {s.strip() for s in os.environ.get("DOEMITZ_SHOTS", "").split(",") if s.strip()}
SHOTS = [shot for shot in ALL_SHOTS if not _subset or shot[0].rsplit(".", 1)[0] in _subset]

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
deadline = monotonic() + 240
shot_idx = 0
state = "warmup"
wait_ticks = 0
captured = []
current_task = None


_sun_rot = None
_sky_int = None


def _set_night(night):
    """Night view for interior shots: sun below the horizon, dim sky light; interior lights stay on."""
    global _sun_rot, _sky_int
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    sun = next((a for a in actors if a.get_actor_label() == "Altstadt Sun"), None)
    sky = next((a for a in actors if a.get_actor_label() == "Altstadt Skylight"), None)
    if sun is None or sky is None:
        return
    sky_comp = sky.get_component_by_class(unreal.SkyLightComponent)
    if _sun_rot is None:
        _sun_rot = sun.get_actor_rotation()
        _sky_int = sky_comp.intensity
    if night:
        sun.set_actor_rotation(unreal.Rotator(pitch=25.0, yaw=_sun_rot.yaw, roll=0.0), False)
        sky_comp.set_intensity(0.08)
    else:
        sun.set_actor_rotation(_sun_rot, False)
        sky_comp.set_intensity(_sky_int)


def finish(msg, ok):
    try:
        _set_night(False)
    except Exception:
        pass
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
            if wait_ticks < 40:
                return
            level.editor_set_game_view(True)
            world = editor.get_editor_world()
            if world is not None:
                # Lumen GI/reflections are a DoemitzHigh option; keep the comparable non-Lumen view of Sprint 12.
                unreal.SystemLibrary.execute_console_command(world, "r.DynamicGlobalIlluminationMethod 0")
                unreal.SystemLibrary.execute_console_command(world, "r.ReflectionMethod 0")
            state = "position"
            wait_ticks = 0
            return

        if state == "position":
            name, loc, target = SHOTS[shot_idx]
            _set_night(name in _NIGHT)
            editor.set_level_viewport_camera_info(loc, look_at_rot(loc, target))
            wait_ticks = 0
            state = "settle"
            return

        if state == "settle":
            wait_ticks += 1
            if wait_ticks < 30:
                return
            out_path = str(OUT_DIR / SHOTS[shot_idx][0])
            current_task = unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, out_path, None, False, False)
            wait_ticks = 0
            state = "wait_shot"
            return

        if state == "wait_shot":
            wait_ticks += 1
            out_file = OUT_DIR / SHOTS[shot_idx][0]
            done = (current_task is not None and current_task.is_task_done()) or (
                out_file.is_file() and out_file.stat().st_size > 1000 and wait_ticks >= 10
            )
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
                finish(f"DOEMITZ_SPRINT13_SCREENSHOTS_OK: {len(captured)}/{len(SHOTS)} saved to {OUT_DIR}", True)
    except Exception:
        finish("DOEMITZ_SPRINT13_SCREENSHOTS_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(tick)
