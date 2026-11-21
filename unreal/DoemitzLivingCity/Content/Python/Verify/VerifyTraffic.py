import json
from pathlib import Path
from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
vehicle_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzTrafficVehicle")
project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
package_path = project.parents[1] / "data/processed/doemitz-altstadt/unreal-city-meshes.json"
package = json.loads(package_path.read_text(encoding="utf-8"))
vehicle_config = package["vehicle"]
route_length = vehicle_config["length_m"] * 100
deadline = monotonic() + 140
phase = "spawn"
previous_distance = None
previous_position = None
stable_since = None
start_distance = None
stopped_distance = None


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def check(_delta_seconds):
    global phase, previous_distance, previous_position, stable_since, start_distance, stopped_distance
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during {phase}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if pawn is None:
            return
        vehicles = unreal.GameplayStatics.get_all_actors_of_class(world, vehicle_class)
        if len(vehicles) != 1:
            raise RuntimeError(f"expected one vehicle, found {len(vehicles)}")
        car = vehicles[0]
        position = car.get_actor_location()
        distance = car.get_distance_along_route()
        time = unreal.GameplayStatics.get_time_seconds(world)
        travel = None if previous_distance is None else (distance - previous_distance) % route_length
        if travel is not None and (position - previous_position).length() > travel + 0.2:
            raise RuntimeError("car position jumped relative to its route progress")
        if phase == "spawn":
            component = car.get_editor_property("vehicle_mesh")
            if component.get_editor_property("static_mesh") is None:
                raise RuntimeError("the vehicle has no visible mesh")
            if abs(distance - vehicle_config["start_distance_m"] * 100) > 100:
                raise RuntimeError("vehicle failed to start near the configured distance")
            start_distance = distance
            crossing = position + car.get_actor_forward_vector() * 480
            crossing.z = pawn.get_actor_location().z
            pawn.set_actor_location(crossing, False, True)
            phase = "yield"
        elif phase == "yield":
            if distance - start_distance > 350:
                raise RuntimeError("vehicle failed to stop for the player")
            if abs(distance - previous_distance) < 0.001:
                stable_since = time if stable_since is None else stable_since
                if time - stable_since >= 0.6:
                    if distance - start_distance < 20:
                        raise RuntimeError("vehicle did not move before stopping")
                    stopped_distance = distance
                    east, north, height = package["sidewalk_probe_m"]
                    half_height = pawn.get_editor_property("capsule_component").get_scaled_capsule_half_height()
                    pawn.set_actor_location(
                        unreal.Vector(north * 100, east * 100, height * 100 + half_height + 5),
                        False, True,
                    )
                    phase = "resume"
            else:
                stable_since = None
        elif phase == "resume" and distance - stopped_distance > 500:
            unreal.GameplayStatics.set_global_time_dilation(world, 10)
            phase = "lap"
        elif phase == "lap" and car.get_completed_laps() >= 1 and distance >= start_distance:
            finish(
                f"DOEMITZ_TRAFFIC_PIE_OK: player stop after {(stopped_distance - start_distance) / 100:.2f} m, "
                f"resumed and completed {route_length / 100:.1f} m loop",
                True,
            )
            return
        previous_distance = distance
        previous_position = position
    except Exception:
        finish("DOEMITZ_TRAFFIC_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
