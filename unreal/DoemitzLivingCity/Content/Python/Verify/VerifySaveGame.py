from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
vehicle_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzTrafficVehicle")
dn_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzDayNightController")
slot_name = "DoemitzVerifySlot"
deadline = monotonic() + 90
phase = "prepare"
saved_player_loc = None
saved_vehicle_dist = None
saved_anna_loc = None
saved_anna_moving = None


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    if unreal.GameplayStatics.does_save_game_exist(slot_name, 0):
        unreal.GameplayStatics.delete_game_in_slot(slot_name, 0)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def get_state(sub, cid):
    res = sub.get_citizen_state(cid)
    return res[1] if isinstance(res, tuple) else res


def check(_delta_seconds):
    global phase, saved_player_loc, saved_vehicle_dist, saved_anna_loc, saved_anna_moving
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during {phase}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if sub is None or sub.get_citizen_count() == 0 or pawn is None:
            return
        vehicles = unreal.GameplayStatics.get_all_actors_of_class(world, vehicle_class)
        dns = unreal.GameplayStatics.get_all_actors_of_class(world, dn_class)
        if len(vehicles) < 1 or len(dns) != 1:
            return
        car = next((v for v in vehicles if str(v.get_vehicle_id()) == "altstadt_vehicle_01"), vehicles[0])
        dn = dns[0]

        if phase == "prepare":
            # Move clock to 07:55 so Anna starts commuting, set 5x speed.
            sub.set_time_of_day_minutes(475.0)
            sub.set_time_scale(300.0)
            unreal.GameplayStatics.set_global_time_dilation(world, 4.0)
            phase = "wait_commute"
            return

        if phase == "wait_commute":
            anna = get_state(sub, "citizen_anna_01")
            if not anna.get_editor_property("is_moving") or anna.get_editor_property("route_progress_cm") < 200.0:
                return

            # Pause and capture reference state before saving.
            sub.set_time_scale(0.0)
            saved_min = sub.get_time_of_day_minutes()
            saved_player_loc = pawn.get_actor_location()
            saved_vehicle_dist = car.get_distance_along_route()
            saved_anna_loc = anna.get_editor_property("world_location")
            saved_anna_moving = anna.get_editor_property("is_moving")

            if not sub.save_city_state(slot_name):
                raise RuntimeError("SaveCityState returned False")
            if not sub.does_save_exist(slot_name):
                raise RuntimeError("Save slot does not exist after SaveCityState")

            # Mutate world state heavily before loading back.
            sub.set_time_of_day_minutes(15.0)
            dn.update_lighting_from_simulation()
            if dn.is_daytime():
                raise RuntimeError("expected night lighting after mutating time to 00:15")
            pawn.set_actor_location(saved_player_loc + unreal.Vector(800.0, 0.0, 0.0), False, True)
            if sub.get_vehicle_count() > 0:
                sub.set_vehicle_edge_position_for_test("altstadt_vehicle_01", "edge:osm:way:157877527:0:0:fwd", 1234.0, 0.0)
            else:
                car.restore_motion_state(saved_vehicle_dist + 5000.0, 3)

            if not sub.load_city_state(slot_name):
                raise RuntimeError("LoadCityState returned False")

            restored_min = sub.get_time_of_day_minutes()
            restored_player = pawn.get_actor_location()
            restored_car_dist = car.get_distance_along_route()
            restored_anna = get_state(sub, "citizen_anna_01")
            restored_anna_loc = restored_anna.get_editor_property("world_location")

            if abs(restored_min - saved_min) > 0.5:
                raise RuntimeError(f"restored time mismatch: {restored_min} vs {saved_min}")
            if not dn.is_daytime():
                raise RuntimeError("day/night controller did not restore daytime after load")
            if (restored_player - saved_player_loc).length() > 5.0:
                raise RuntimeError("player location was not restored")
            if abs(restored_car_dist - saved_vehicle_dist) > 5.0:
                raise RuntimeError(f"vehicle distance mismatch: {restored_car_dist} vs {saved_vehicle_dist}")
            if restored_anna.get_editor_property("is_moving") != saved_anna_moving:
                raise RuntimeError("citizen moving state was not restored")
            if (restored_anna_loc - saved_anna_loc).length() > 5.0:
                raise RuntimeError("citizen location was not restored")

            # Also verify SaveSchemaVersion 2 -> 3 migration (weekday defaults to Monday, 30 citizens valid)
            v2_slot = "DoemitzVerifyV2Migration"
            v2_save = unreal.GameplayStatics.create_save_game_object(unreal.DoemitzSaveGame)
            v2_save.set_editor_property("save_schema_version", 2)
            v2_save.set_editor_property("day_number", 4)
            v2_save.set_editor_property("time_of_day_minutes", 600.0)
            v2_save.set_editor_property("time_scale", 60.0)
            if not unreal.GameplayStatics.save_game_to_slot(v2_save, v2_slot, 0):
                raise RuntimeError("failed to write synthetic v2 save")
            sub.set_day_number(5)
            if not sub.load_city_state(v2_slot):
                raise RuntimeError("LoadCityState failed to migrate SaveSchemaVersion 2")
            if sub.get_day_number() != 4 or sub.get_day_of_week() != 0 or abs(sub.get_time_of_day_minutes() - 600.0) > 1.0:
                raise RuntimeError(
                    f"v2 migration did not restore day/Monday/time: day={sub.get_day_number()} dow={sub.get_day_of_week()} min={sub.get_time_of_day_minutes()}"
                )
            if sub.get_citizen_count() != 30:
                raise RuntimeError(f"expected 30 citizens after v2 migration, got {sub.get_citizen_count()}")
            unreal.GameplayStatics.delete_game_in_slot(v2_slot, 0)

            finish(
                f"DOEMITZ_SAVEGAME_PIE_OK: v3 saved & restored time={restored_min:.1f}m, "
                f"30 citizens, player/vehicle states, daytime lighting, and v2->v3 migration verified",
                True,
            )
            phase = "done"
    except Exception:
        phase = "done"
        finish("DOEMITZ_SAVEGAME_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
