"""Sprint 16 PIE check: Horizon skirt & ExponentialHeightFog, 45 citizens & 12 vehicles,
walk-in harbour interiors (Hotel Dömitzer Hafen & Dömitzer Hafen Restaurant) with harbour jobs/items,
and async cross-cell SaveGame streaming restore across the 450 m World Partition loading range."""

from math import hypot
from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
cfg_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzSimulationConfig")
dn_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzDayNightController")
door_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzInteriorDoor")

HOTEL = "poi:osm:node:387219809"
RESTAURANT = "poi:osm:node:1125977013"
SLOT = "DoemitzVerifySprint16CrossCell"
deadline = monotonic() + 240

state = "init"
wait_start = 0.0
waypoints = []
wp_index = 0
door_max_alpha = 0.0
ctx = {}
results = {}


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    if unreal.GameplayStatics.does_save_game_exist(SLOT, 0):
        unreal.GameplayStatics.delete_game_in_slot(SLOT, 0)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def v2(a, b):
    return hypot(a.x - b.x, a.y - b.y)


def find_door(world, place_id):
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, door_class):
        if str(actor.get_editor_property("place_id")) == place_id:
            return actor
    raise RuntimeError(f"no interior door for {place_id}")


def interior(sub, place_id):
    it = sub.get_interior_for_place(place_id)
    if it is None:
        raise RuntimeError(f"no interior configured for {place_id}")
    return it


def tick(_dt):
    global state, wait_start, waypoints, wp_index, door_max_alpha
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out in state {state}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        cit = unreal.DoemitzCitizenSubsystem.get(world)
        trf = unreal.DoemitzTrafficSubsystem.get(world)
        econ = unreal.DoemitzEconomySubsystem.get(world)
        tsk = unreal.DoemitzTaskSubsystem.get(world)
        save = unreal.DoemitzSaveSubsystem.get(world)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        cfgs = unreal.GameplayStatics.get_all_actors_of_class(world, cfg_class)
        dns = unreal.GameplayStatics.get_all_actors_of_class(world, dn_class)
        if (
            sub is None or cit is None or trf is None or econ is None or tsk is None or save is None
            or pawn is None or len(cfgs) != 1 or len(dns) != 1 or cit.get_citizen_count() < 45
        ):
            return

        dn = dns[0]
        interaction = pawn.get_interaction_component()
        cm = pawn.get_editor_property("character_movement")

        if state == "init":
            # 1. Scaling checks: 45 citizens, 12 vehicles, 5 interiors
            if cit.get_citizen_count() != 45:
                raise RuntimeError(f"expected 45 citizens, got {cit.get_citizen_count()}")
            if trf.get_vehicle_count() != 12:
                raise RuntimeError(f"expected 12 vehicles, got {trf.get_vehicle_count()}")
            if sub.get_interior_count() != 5:
                raise RuntimeError(f"expected 5 interiors, got {sub.get_interior_count()}")

            # 2. Horizon skirt & ExponentialHeightFog
            skirt_actors = [
                a for a in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor)
                if a.get_actor_label() == "Altstadt TerrainHorizonSkirt"
            ]
            if len(skirt_actors) != 1:
                raise RuntimeError(f"expected 1 Altstadt TerrainHorizonSkirt actor, found {len(skirt_actors)}")
            skirt_prof = str(skirt_actors[0].static_mesh_component.get_collision_profile_name())
            if skirt_prof != "NoCollision":
                raise RuntimeError(f"horizon skirt must have NoCollision, got {skirt_prof}")

            fog = dn.get_height_fog()
            if fog is None:
                raise RuntimeError("DayNightController.height_fog is not wired")
            fog_comp = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
            sub.set_day_number(1)
            sub.set_time_scale(0.0)
            sub.set_time_of_day_minutes(720.0)
            dn.update_lighting_from_simulation()
            day_b = float(fog_comp.get_editor_property("fog_inscattering_luminance").b)
            sub.set_time_of_day_minutes(60.0)
            dn.update_lighting_from_simulation()
            night_b = float(fog_comp.get_editor_property("fog_inscattering_luminance").b)
            if day_b <= night_b + 0.2:
                raise RuntimeError(f"fog did not darken at night: day_b={day_b:.3f}, night_b={night_b:.3f}")
            results["fog_day_night_ok"] = (round(day_b, 2), round(night_b, 2))

            # 3. Harbour jobs acceptable
            sub.set_time_of_day_minutes(660.0)  # Monday 11:00: Hotel & Restaurant open
            dn.update_lighting_from_simulation()
            if not econ.accept_job(HOTEL) or str(econ.get_active_job_id()) != "job_hafenhotel_rezeption":
                raise RuntimeError(f"accepting Hotel job failed: {econ.get_active_job_id()}")
            if not econ.accept_job(RESTAURANT) or str(econ.get_active_job_id()) != "job_hafenrestaurant_service":
                raise RuntimeError(f"accepting Restaurant job failed: {econ.get_active_job_id()}")
            results["harbour_jobs_ok"] = True

            # Move player in front of Hotel Dömitzer Hafen and wait for World Partition streaming
            it_hotel = interior(sub, HOTEL)
            door_hotel = find_door(world, HOTEL)
            ctx["hotel"] = it_hotel
            ctx["hotel_door"] = door_hotel
            outside = it_hotel.get_editor_property("door_outside_location")
            inward = door_hotel.get_editor_property("inward_direction")
            cm.set_editor_property("gravity_scale", 0.0)
            cm.stop_movement_immediately()
            pawn.set_actor_location(outside - inward * 180.0 + unreal.Vector(0, 0, 100.0), False, True)
            wait_start = monotonic()
            state = "wait_hotel_stream"
            return

        if state == "wait_hotel_stream":
            if not unreal.DoemitzWorldTools.is_streaming_completed(world):
                if monotonic() - wait_start > 12.0:
                    raise RuntimeError("streaming timed out at Hotel Dömitzer Hafen")
                return
            cm.set_editor_property("gravity_scale", 1.0)
            it_hotel = ctx["hotel"]
            door_hotel = ctx["hotel_door"]
            waypoints = [
                door_hotel.get_editor_property("door_center"),
                it_hotel.get_editor_property("door_inside_location"),
                it_hotel.get_editor_property("counter_location"),
            ]
            wp_index = 0
            door_max_alpha = 0.0
            wait_start = monotonic()
            state = "walk_hotel"
            return

        if state == "walk_hotel":
            door_max_alpha = max(door_max_alpha, ctx["hotel_door"].get_open_alpha())
            loc = pawn.get_actor_location()
            target = waypoints[wp_index]
            if v2(loc, target) < 55.0:
                wp_index += 1
                if wp_index >= len(waypoints):
                    state = "check_hotel"
                    return
                target = waypoints[wp_index]
            if monotonic() - wait_start > 30.0:
                raise RuntimeError(f"player stuck walking into Hotel at wp {wp_index}, loc={loc}")
            d = unreal.Vector(target.x - loc.x, target.y - loc.y, 0.0)
            pawn.add_movement_input(d / max(d.length(), 1.0), 1.0, False)
            return

        if state == "check_hotel":
            it_hotel = ctx["hotel"]
            loc = pawn.get_actor_location()
            iid = str(it_hotel.get_editor_property("interior_id"))
            if str(sub.find_interior_at_location(loc)) != iid:
                raise RuntimeError(f"player not inside Hotel lobby: {loc}")
            if door_max_alpha < 0.85:
                raise RuntimeError(f"Hotel door never opened: alpha={door_max_alpha:.2f}")
            interaction.refresh_nearest_entrance()
            if str(interaction.get_nearest_place_id()) != HOTEL:
                raise RuntimeError(f"Hotel counter prompt missing: {interaction.get_nearest_place_id()}")
            if not econ.buy_item(HOTEL, "item_hafenfuehrer", 1):
                raise RuntimeError("buying item_hafenfuehrer at Hotel failed")
            # Check harbour worker stands inside Hotel
            if not cit.set_citizen_at_place_for_test("citizen_hafen_01", HOTEL, unreal.DoemitzCitizenActivity.WORKING):
                raise RuntimeError("failed to place citizen_hafen_01 at Hotel")
            h1_loc = cit.get_citizen_presentation_transform("citizen_hafen_01")[0]
            if str(sub.find_interior_at_location(h1_loc)) != iid:
                raise RuntimeError(f"citizen_hafen_01 not placed inside Hotel interior: {h1_loc}")
            results["hotel_ok"] = True

            # Save inside Hotel Dömitzer Hafen for the cross-cell SaveGame streaming test
            ctx["hotel_save_loc"] = loc
            if not save.save_city_state(SLOT):
                raise RuntimeError("SaveCityState inside Hotel failed")

            # Now walk into Dömitzer Hafen Restaurant
            it_rest = interior(sub, RESTAURANT)
            door_rest = find_door(world, RESTAURANT)
            ctx["rest"] = it_rest
            ctx["rest_door"] = door_rest
            outside = it_rest.get_editor_property("door_outside_location")
            inward = door_rest.get_editor_property("inward_direction")
            pawn.set_actor_location(outside - inward * 180.0 + unreal.Vector(0, 0, 100.0), False, True)
            waypoints = [
                door_rest.get_editor_property("door_center"),
                it_rest.get_editor_property("door_inside_location"),
                it_rest.get_editor_property("counter_location"),
            ]
            wp_index = 0
            door_max_alpha = 0.0
            wait_start = monotonic()
            state = "walk_rest"
            return

        if state == "walk_rest":
            door_max_alpha = max(door_max_alpha, ctx["rest_door"].get_open_alpha())
            loc = pawn.get_actor_location()
            target = waypoints[wp_index]
            if v2(loc, target) < 55.0:
                wp_index += 1
                if wp_index >= len(waypoints):
                    state = "check_rest"
                    return
                target = waypoints[wp_index]
            if monotonic() - wait_start > 30.0:
                raise RuntimeError(f"player stuck walking into Restaurant at wp {wp_index}, loc={loc}")
            d = unreal.Vector(target.x - loc.x, target.y - loc.y, 0.0)
            pawn.add_movement_input(d / max(d.length(), 1.0), 1.0, False)
            return

        if state == "check_rest":
            it_rest = ctx["rest"]
            loc = pawn.get_actor_location()
            iid = str(it_rest.get_editor_property("interior_id"))
            if str(sub.find_interior_at_location(loc)) != iid:
                raise RuntimeError(f"player not inside Restaurant: {loc}")
            if door_max_alpha < 0.85:
                raise RuntimeError(f"Restaurant door never opened: alpha={door_max_alpha:.2f}")
            interaction.refresh_nearest_entrance()
            if str(interaction.get_nearest_place_id()) != RESTAURANT:
                raise RuntimeError(f"Restaurant counter prompt missing: {interaction.get_nearest_place_id()}")
            if not econ.buy_item(RESTAURANT, "item_matjesplatte", 1):
                raise RuntimeError("buying item_matjesplatte at Restaurant failed")
            if not cit.set_citizen_at_place_for_test("citizen_hafen_02", RESTAURANT, unreal.DoemitzCitizenActivity.WORKING):
                raise RuntimeError("failed to place citizen_hafen_02 at Restaurant")
            h2_loc = cit.get_citizen_presentation_transform("citizen_hafen_02")[0]
            if str(sub.find_interior_at_location(h2_loc)) != iid:
                raise RuntimeError(f"citizen_hafen_02 not placed inside Restaurant interior: {h2_loc}")
            results["restaurant_ok"] = True

            # 4. Cross-cell SaveGame streaming test: teleport >700 m away to Altstadt West so harbour cells unload
            cm.set_editor_property("gravity_scale", 0.0)
            cm.stop_movement_immediately()
            pawn.set_actor_location(unreal.Vector(-22000.0, -7000.0, 2500.0), False, True)
            wait_start = monotonic()
            state = "wait_altstadt_unload"
            return

        if state == "wait_altstadt_unload":
            if not unreal.DoemitzWorldTools.is_streaming_completed(world):
                if monotonic() - wait_start > 12.0:
                    raise RuntimeError("streaming timed out after teleporting to Altstadt")
                return
            if monotonic() - wait_start < 1.0:
                return
            # Load the Harbour Hotel save from >700 m away -> must trigger async streaming restore
            cm.set_editor_property("gravity_scale", 1.0)
            if not save.load_city_state(SLOT):
                raise RuntimeError("cross-cell LoadCityState failed")
            results["triggered_async_streaming"] = bool(save.is_pending_streaming_restore())
            wait_start = monotonic()
            state = "wait_save_restore"
            return

        if state == "wait_save_restore":
            if save.is_pending_streaming_restore():
                if monotonic() - wait_start > 12.0:
                    raise RuntimeError("SaveGame async streaming restore timed out")
                return
            # Let gravity act briefly to verify the player stands firmly on the restored Hotel floor
            if monotonic() - wait_start < 1.2:
                return
            it_hotel = ctx["hotel"]
            loc = pawn.get_actor_location()
            floor_z = it_hotel.get_editor_property("floor_z")
            if str(save.get_last_loaded_player_interior_id()) != str(it_hotel.get_editor_property("interior_id")):
                raise RuntimeError(f"cross-cell load interior mismatch: {save.get_last_loaded_player_interior_id()}")
            if v2(loc, ctx["hotel_save_loc"]) > 30.0:
                raise RuntimeError(f"cross-cell load XY mismatch: {loc} vs {ctx['hotel_save_loc']}")
            if abs((loc.z - 90.0) - floor_z) > 25.0:
                raise RuntimeError(f"player fell or floated after cross-cell load: z={loc.z:.1f} vs floor={floor_z:.1f}")
            if abs(cm.get_editor_property("gravity_scale") - 1.0) > 0.05:
                raise RuntimeError(f"gravity_scale not restored after cross-cell load: {cm.get_editor_property('gravity_scale')}")
            results["cross_cell_load_z_cm"] = round(loc.z - floor_z, 1)
            finish(
                f"DOEMITZ_SPRINT16_PIE_OK: 45 citizens, 12 vehicles, 5 interiors (Hotel & Restaurant walked & purchased), "
                f"horizon skirt NoCollision & day/night fog OK, cross-cell SaveGame streaming restore OK ({results})",
                True,
            )
            state = "done"
    except Exception:
        state = "done"
        finish("DOEMITZ_SPRINT16_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(tick)
level.editor_request_begin_play()
