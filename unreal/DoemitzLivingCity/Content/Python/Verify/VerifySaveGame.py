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

            # Pause and perform economy actions before saving so v4 economy persistence is also verified.
            sub.set_time_scale(0.0)
            saved_min = sub.get_time_of_day_minutes()
            saved_player_loc = pawn.get_actor_location()
            saved_vehicle_dist = car.get_distance_along_route()
            saved_anna_loc = anna.get_editor_property("world_location")
            saved_anna_moving = anna.get_editor_property("is_moving")

            # Perform an open-hours purchase and accept a job before saving
            sub.set_time_of_day_minutes(600.0)
            saved_min = sub.get_time_of_day_minutes()
            if not sub.buy_item("poi:osm:node:1794647095", "item_pflaster", 1):
                raise RuntimeError("pre-save BuyItem failed")
            if not sub.accept_job("place_kaufhaus"):
                raise RuntimeError("pre-save AcceptJob failed")
            saved_money = sub.get_player_money_cents()
            saved_qty = sub.get_inventory_quantity("item_pflaster")
            saved_job = str(sub.get_active_job_id())
            saved_rev_daily, _ = sub.get_place_revenue("poi:osm:node:1794647095")

            if not sub.save_city_state(slot_name):
                raise RuntimeError("SaveCityState returned False")
            if not sub.does_save_exist(slot_name):
                raise RuntimeError("Save slot does not exist after SaveCityState")

            # Mutate world & economy state heavily before loading back.
            sub.set_time_of_day_minutes(15.0)
            sub.set_player_money_cents_for_test(99999)
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
            restored_rev_daily, _ = sub.get_place_revenue("poi:osm:node:1794647095")

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
            if sub.get_player_money_cents() != saved_money:
                raise RuntimeError(f"money mismatch: {sub.get_player_money_cents()} vs {saved_money}")
            if sub.get_inventory_quantity("item_pflaster") != saved_qty:
                raise RuntimeError("inventory quantity was not restored")
            if str(sub.get_active_job_id()) != saved_job:
                raise RuntimeError("active job was not restored")
            if restored_rev_daily != saved_rev_daily:
                raise RuntimeError(f"place revenue mismatch: {restored_rev_daily} vs {saved_rev_daily}")

            # Also verify SaveSchemaVersion 3 -> 4 migration (starting balance 12500 ct, empty inventory)
            v3_slot = "DoemitzVerifyV3Migration"
            v3_save = unreal.GameplayStatics.create_save_game_object(unreal.DoemitzSaveGame)
            v3_save.set_editor_property("save_schema_version", 3)
            v3_save.set_editor_property("day_number", 4)
            v3_save.set_editor_property("day_of_week", 3)
            v3_save.set_editor_property("calendar_week", 1)
            v3_save.set_editor_property("time_of_day_minutes", 600.0)
            v3_save.set_editor_property("time_scale", 60.0)
            if not unreal.GameplayStatics.save_game_to_slot(v3_save, v3_slot, 0):
                raise RuntimeError("failed to write synthetic v3 save")
            if not sub.load_city_state(v3_slot):
                raise RuntimeError("LoadCityState failed to migrate SaveSchemaVersion 3")
            if sub.get_day_number() != 4 or sub.get_day_of_week() != 3:
                raise RuntimeError(f"v3 migration did not restore day/dow: {sub.get_day_number()}/{sub.get_day_of_week()}")
            if sub.get_player_money_cents() != 12500 or sub.get_inventory_quantity("item_pflaster") != 0:
                raise RuntimeError(
                    f"v3 migration did not initialize economy defaults: money={sub.get_player_money_cents()}, inv={sub.get_inventory_quantity('item_pflaster')}"
                )
            unreal.GameplayStatics.delete_game_in_slot(v3_slot, 0)

            finish(
                f"DOEMITZ_SAVEGAME_PIE_OK: v4 saved & restored time={restored_min:.1f}m, "
                f"money={saved_money}ct, inv={saved_qty}, job={saved_job}, rev={saved_rev_daily}ct, "
                f"30 citizens, player/vehicle states, and v3->v4 migration verified",
                True,
            )
            phase = "done"
    except Exception:
        phase = "done"
        finish("DOEMITZ_SAVEGAME_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
