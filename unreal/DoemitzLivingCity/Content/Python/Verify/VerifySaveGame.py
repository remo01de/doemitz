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


def get_vstate(sub, vid):
    res = sub.get_vehicle_state(vid)
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
            sub.set_time_of_day_minutes(475.0)
            sub.set_time_scale(300.0)
            unreal.GameplayStatics.set_global_time_dilation(world, 4.0)
            phase = "wait_commute"
            return

        if phase == "wait_commute":
            anna = get_state(sub, "citizen_anna_01")
            if not anna.get_editor_property("is_moving") or anna.get_editor_property("route_progress_cm") < 200.0:
                return

            sub.set_time_scale(0.0)
            saved_player_loc = pawn.get_actor_location()
            saved_vehicle_dist = car.get_distance_along_route()
            saved_anna_loc = anna.get_editor_property("world_location")
            saved_anna_moving = anna.get_editor_property("is_moving")

            # Perform economy & task actions before saving v5
            sub.set_time_of_day_minutes(600.0)
            saved_min = sub.get_time_of_day_minutes()
            if not sub.buy_item("poi:osm:node:1794647095", "item_pflaster", 1):
                raise RuntimeError("pre-save BuyItem failed")
            if not sub.accept_job("place_kaufhaus"):
                raise RuntimeError("pre-save AcceptJob failed")

            avail_tasks = sub.get_tasks_by_status(unreal.DoemitzTaskStatus.AVAILABLE)
            if len(avail_tasks) < 2:
                raise RuntimeError(f"expected >=2 available tasks, got {len(avail_tasks)}")
            accepted_task_id = str(avail_tasks[0].get_editor_property("task_id"))
            if not sub.accept_task(accepted_task_id):
                raise RuntimeError(f"AcceptTask({accepted_task_id}) failed")

            saved_money = sub.get_player_money_cents()
            saved_qty = sub.get_inventory_quantity("item_pflaster")
            saved_job = str(sub.get_active_job_id())
            saved_rev_daily, _ = sub.get_place_revenue("poi:osm:node:1794647095")
            saved_active_count = len(sub.get_tasks_by_status(unreal.DoemitzTaskStatus.ACTIVE))

            if not sub.save_city_state(slot_name):
                raise RuntimeError("SaveCityState returned False")
            if not sub.does_save_exist(slot_name):
                raise RuntimeError("Save slot does not exist after SaveCityState")

            # Mutate world, economy, and task state heavily before loading back
            sub.set_time_of_day_minutes(1430.0)  # Expires active task -> MISSED
            if len(sub.get_tasks_by_status(unreal.DoemitzTaskStatus.ACTIVE)) != 0:
                raise RuntimeError("expected active task to expire when mutating time to 23:50")
            sub.set_time_of_day_minutes(15.0)
            sub.set_player_money_cents_for_test(99999)
            dn.update_lighting_from_simulation()
            if dn.is_daytime():
                raise RuntimeError("expected night lighting after mutating time to 00:15")
            pawn.set_actor_location(saved_player_loc + unreal.Vector(800.0, 0.0, 0.0), False, True)
            sub.set_vehicle_edge_position_for_test("altstadt_vehicle_01", "edge:osm:way:157877527:0:0:fwd", 1234.0, 0.0)

            if not sub.load_city_state(slot_name):
                raise RuntimeError("LoadCityState returned False")

            restored_min = sub.get_time_of_day_minutes()
            restored_player = pawn.get_actor_location()
            restored_car_dist = car.get_distance_along_route()
            restored_anna = get_state(sub, "citizen_anna_01")
            restored_anna_loc = restored_anna.get_editor_property("world_location")
            restored_rev_daily, _ = sub.get_place_revenue("poi:osm:node:1794647095")
            restored_active = sub.get_tasks_by_status(unreal.DoemitzTaskStatus.ACTIVE)

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
            if len(restored_active) != saved_active_count or str(restored_active[0].get_editor_property("task_id")) != accepted_task_id:
                raise RuntimeError("active task was not restored from SaveGame v5")

            # Verify SaveSchemaVersion 4 -> 5 migration (vehicles Driving, 0 tasks, economy preserved)
            v4_slot = "DoemitzVerifyV4Migration"
            v4_save = unreal.GameplayStatics.create_save_game_object(unreal.DoemitzSaveGame)
            v4_save.set_editor_property("save_schema_version", 4)
            v4_save.set_editor_property("day_number", 3)
            v4_save.set_editor_property("day_of_week", 2)
            v4_save.set_editor_property("calendar_week", 1)
            v4_save.set_editor_property("time_of_day_minutes", 600.0)
            v4_save.set_editor_property("time_scale", 60.0)
            v4_save.set_editor_property("player_money_cents", 18800)
            if not unreal.GameplayStatics.save_game_to_slot(v4_save, v4_slot, 0):
                raise RuntimeError("failed to write synthetic v4 save")
            if not sub.load_city_state(v4_slot):
                raise RuntimeError("LoadCityState failed to migrate SaveSchemaVersion 4")
            if sub.get_day_number() != 3 or sub.get_day_of_week() != 2:
                raise RuntimeError(f"v4 migration did not restore day/dow: {sub.get_day_number()}/{sub.get_day_of_week()}")
            if sub.get_player_money_cents() != 18800:
                raise RuntimeError(f"v4 migration did not preserve money: {sub.get_player_money_cents()}")
            if len(sub.get_all_tasks()) != 0:
                raise RuntimeError(f"v4 migration expected 0 tasks, got {len(sub.get_all_tasks())}")
            for vid in sub.get_all_vehicle_ids():
                vst = get_vstate(sub, vid)
                if vst.get_editor_property("phase") != unreal.DoemitzVehiclePhase.DRIVING:
                    raise RuntimeError(f"v4 migration expected vehicle {vid} in DRIVING phase")
            unreal.GameplayStatics.delete_game_in_slot(v4_slot, 0)

            # Verify SaveSchemaVersion 5 -> 6 terrain height migration (flat Z -> downward trace onto DGM1)
            v5_slot = "DoemitzVerifyV5Migration"
            pawn.set_actor_location(unreal.Vector(saved_player_loc.x, saved_player_loc.y, 96.0), False, True)
            sub.set_citizen_position_for_test("citizen_anna_01", unreal.Vector(saved_anna_loc.x, saved_anna_loc.y, 20.0))
            sub.set_player_money_cents_for_test(21500)
            if not sub.save_city_state(v5_slot):
                raise RuntimeError("failed to capture baseline save for v5 migration")
            v5_save = unreal.GameplayStatics.load_game_from_slot(v5_slot, 0)
            v5_save.set_editor_property("save_schema_version", 5)
            v5_save.set_editor_property("day_number", 4)
            if not unreal.GameplayStatics.save_game_to_slot(v5_save, v5_slot, 0):
                raise RuntimeError("failed to write downgraded v5 save")

            if not sub.load_city_state(v5_slot):
                raise RuntimeError("LoadCityState failed to migrate SaveSchemaVersion 5")
            if sub.get_day_number() != 4 or sub.get_player_money_cents() != 21500:
                raise RuntimeError(f"v5 migration state mismatch: day={sub.get_day_number()}, money={sub.get_player_money_cents()}")
            mig_player_z = pawn.get_actor_location().z
            mig_anna_z = get_state(sub, "citizen_anna_01").get_editor_property("world_location").z
            # On real DGM1 terrain, Goethestrasse/Rathausplatz is ~470-490 cm above local origin (far above flat 20/96 cm)
            if abs(mig_player_z - saved_player_loc.z) > 45.0:
                raise RuntimeError(
                    f"v5->v6 player height not snapped to terrain: got {mig_player_z:.1f} cm vs expected ~{saved_player_loc.z:.1f} cm"
                )
            if abs(mig_anna_z - saved_anna_loc.z) > 45.0:
                raise RuntimeError(
                    f"v5->v6 citizen height not snapped to terrain: got {mig_anna_z:.1f} cm vs expected ~{saved_anna_loc.z:.1f} cm"
                )
            unreal.GameplayStatics.delete_game_in_slot(v5_slot, 0)

            finish(
                f"DOEMITZ_SAVEGAME_PIE_OK: v6 saved & restored time={restored_min:.1f}m, "
                f"money={saved_money}ct, inv={saved_qty}, job={saved_job}, active_task={accepted_task_id}, "
                f"30 citizens, 8 vehicles, v4->v6 and v5->v6 terrain height migration "
                f"(player_z={mig_player_z:.1f}cm, citizen_z={mig_anna_z:.1f}cm) verified",
                True,
            )
            phase = "done"
    except Exception:
        phase = "done"
        finish("DOEMITZ_SAVEGAME_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
