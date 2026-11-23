import json
from pathlib import Path
from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
cfg_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzSimulationConfig")
deadline = monotonic() + 90
done = False
_project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
MAP_PX = int(json.loads((_project.parents[1] / "data/processed/doemitz-altstadt/unreal-city-meshes.json")
                        .read_text(encoding="utf-8"))["city_map"]["width_px"])  # 4096 since Sprint 14


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def get_state(sub, cid):
    res = sub.get_citizen_state(cid)
    return res[1] if isinstance(res, tuple) else res


def check(_delta_seconds):
    global done
    try:
        if done:
            return
        if monotonic() > deadline:
            raise RuntimeError("timed out waiting for city map verification")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        cfgs = unreal.GameplayStatics.get_all_actors_of_class(world, cfg_class)
        if sub is None or sub.get_citizen_count() < 30 or pawn is None or len(cfgs) != 1:
            return
        cfg = cfgs[0]

        # Verify offline map texture and bounds were imported
        tex = sub.get_city_map_texture()
        if tex is None:
            raise RuntimeError("CityMapTexture is None on simulation subsystem")
        bounds = sub.get_city_map_bounds()
        if bounds.get_editor_property("width_px") != MAP_PX or bounds.get_editor_property("height_px") != MAP_PX:
            raise RuntimeError(f"unexpected map texture dimensions: {bounds}")

        # Shrink LOD radius to 15 m so distant citizens have NO active Actor
        sub.set_citizen_lod_radius_cm(1500.0)
        far_cid = None
        for cid in sub.get_all_citizen_ids():
            if not sub.is_citizen_high_detail(cid):
                far_cid = cid
                break
        if far_cid is None:
            raise RuntimeError("could not find a citizen without an active Actor for off-pool map marker test")
        actor_loc_res = sub.get_citizen_actor_location(far_cid)
        has_actor = actor_loc_res[0] if isinstance(actor_loc_res, tuple) else bool(actor_loc_res)
        if has_actor:
            raise RuntimeError(f"expected citizen {far_cid} to have no active Actor")

        # Open UMG City Map
        cfg.set_city_map_open(True)
        if not cfg.is_city_map_open():
            raise RuntimeError("SetCityMapOpen(True) did not open CityMapWidget")
        map_widget = cfg.get_city_map_widget()
        if map_widget is None:
            raise RuntimeError("GetCityMapWidget() returned None")
        map_widget.refresh_map_data()

        # Verify mandatory OSM and GeoBasis-DE/M-V attribution text
        attr = map_widget.get_attribution_text_string()
        if "OpenStreetMap" not in attr or "\u00a9 GeoBasis-DE/M-V" not in attr:
            raise RuntimeError(f"unexpected map attribution (missing OSM or GeoBasis): {attr!r}")

        # Verify marker counts come from simulation state
        if map_widget.get_citizen_marker_count() != 30:
            raise RuntimeError(f"expected 30 citizen markers, got {map_widget.get_citizen_marker_count()}")
        if map_widget.get_vehicle_marker_count() != 8:
            raise RuntimeError(f"expected 8 vehicle markers, got {map_widget.get_vehicle_marker_count()}")
        if map_widget.get_parking_marker_count() < 9:
            raise RuntimeError(f"expected >=9 parking markers, got {map_widget.get_parking_marker_count()}")
        if map_widget.get_place_marker_count() < 25:
            raise RuntimeError(f"expected >=25 place markers, got {map_widget.get_place_marker_count()}")

        # Verify player marker normalized position matches direct projection
        player_loc = pawn.get_actor_location()
        expected_player_uv = sub.project_world_to_normalized_map(player_loc)
        actual_player_uv = map_widget.get_player_normalized_position()
        if abs(actual_player_uv.x - expected_player_uv.x) > 1e-4 or abs(actual_player_uv.y - expected_player_uv.y) > 1e-4:
            raise RuntimeError(f"player map UV mismatch: {actual_player_uv} vs {expected_player_uv}")
        if not (0.0 <= actual_player_uv.x <= 1.0 and 0.0 <= actual_player_uv.y <= 1.0):
            raise RuntimeError(f"player UV out of map bounds: {actual_player_uv}")

        # Verify off-pool citizen (no Actor!) marker normalized position matches simulation state
        far_state = get_state(sub, far_cid)
        expected_far_uv = sub.project_world_to_normalized_map(far_state.get_editor_property("world_location"))
        far_res = map_widget.get_citizen_normalized_position(far_cid)
        far_ok, actual_far_uv = far_res if isinstance(far_res, tuple) else (True, far_res)
        if not far_ok:
            raise RuntimeError(f"GetCitizenNormalizedPosition({far_cid}) returned False")
        if abs(actual_far_uv.x - expected_far_uv.x) > 1e-4 or abs(actual_far_uv.y - expected_far_uv.y) > 1e-4:
            raise RuntimeError(f"off-pool citizen UV mismatch: {actual_far_uv} vs {expected_far_uv}")
        if not (0.0 <= actual_far_uv.x <= 1.0 and 0.0 <= actual_far_uv.y <= 1.0):
            raise RuntimeError(f"off-pool citizen UV out of map bounds: {actual_far_uv}")

        # Verify zoom control and close
        map_widget.set_zoom_level_for_test(2.5)
        if abs(map_widget.get_zoom_level() - 2.5) > 1e-3:
            raise RuntimeError(f"zoom control failed: {map_widget.get_zoom_level()}")
        cfg.set_city_map_open(False)
        if cfg.is_city_map_open():
            raise RuntimeError("SetCityMapOpen(False) did not close CityMapWidget")

        done = True
        finish(
            f"DOEMITZ_MAP_PIE_OK: {MAP_PX}x{MAP_PX} texture loaded, 30 citizens / 8 vehicles / "
            f"{map_widget.get_parking_marker_count()} parking lots / {map_widget.get_place_marker_count()} places, "
            f"player_uv=({actual_player_uv.x:.3f},{actual_player_uv.y:.3f}), "
            f"off_pool_citizen={far_cid} uv=({actual_far_uv.x:.3f},{actual_far_uv.y:.3f}), attribution OK",
            True,
        )
    except Exception:
        done = True
        finish("DOEMITZ_MAP_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
