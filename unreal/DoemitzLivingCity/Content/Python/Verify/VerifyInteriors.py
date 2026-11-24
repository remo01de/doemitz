"""Sprint 13 PIE check: walk-in interiors (door, counter, notice board, citizens inside, save/load inside)."""

from math import hypot
from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
cfg_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzSimulationConfig")
door_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzInteriorDoor")
APOTHEKE = "poi:osm:node:1794647095"
KAUFHAUS = "place_kaufhaus"
RATHAUS = "poi:osm:way:41020272"
SLOT = "DoemitzVerifyInteriorSave"
deadline = monotonic() + 170

state = "init"
ticks = 0
waypoints = []
wp_index = 0
walk_start = 0.0
door_max_alpha = 0.0
results = {}
ctx = {}


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
    global state, ticks, waypoints, wp_index, walk_start, door_max_alpha
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
        econ = unreal.DoemitzEconomySubsystem.get(world)
        tsk = unreal.DoemitzTaskSubsystem.get(world)
        save = unreal.DoemitzSaveSubsystem.get(world)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        cfgs = unreal.GameplayStatics.get_all_actors_of_class(world, cfg_class)
        if sub is None or cit is None or econ is None or tsk is None or save is None or pawn is None or len(cfgs) != 1 or cit.get_citizen_count() == 0:
            return
        interaction = pawn.get_interaction_component()

        if state == "init":
            if sub.get_interior_count() != 5:
                raise RuntimeError(f"expected 5 interiors (3 Altstadt + 2 Harbour), got {sub.get_interior_count()}")
            # Sprint 15/16: DoemitzLow must NEVER hide interior ceiling lights (only street lamps are throttled).
            interior_lights = [
                act for act in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.PointLight)
                if act.get_actor_label().startswith("Altstadt InteriorLight ")
            ]
            if len(interior_lights) < 30:
                raise RuntimeError(f"expected >=30 interior ceiling lights across 5 interiors, found {len(interior_lights)}")
            hidden_lights = [
                act.get_actor_label() for act in interior_lights
                if act.get_editor_property("hidden") or not act.get_component_by_class(unreal.PointLightComponent).is_visible()
            ]
            if hidden_lights:
                raise RuntimeError(f"DoemitzLow hid interior lights: {hidden_lights[:5]}")
            results["interior_lights_visible"] = len(interior_lights)
            sub.set_day_number(1)
            sub.set_time_of_day_minutes(600.0)  # Monday 10:00, Apotheke open
            sub.set_time_scale(0.0)
            it = interior(sub, APOTHEKE)
            ctx["apo"] = it
            ctx["door"] = find_door(world, APOTHEKE)
            outside = it.get_editor_property("door_outside_location")
            inward = ctx["door"].get_editor_property("inward_direction")
            start = outside - inward * 150.0
            pawn.set_actor_location(start + unreal.Vector(0, 0, 95.0), False, True)
            center = ctx["door"].get_editor_property("door_center")
            waypoints = [center, it.get_editor_property("door_inside_location"), it.get_editor_property("counter_location")]
            wp_index = 0
            walk_start = monotonic()
            state = "walk_in"
            return

        if state == "walk_in":
            door_max_alpha = max(door_max_alpha, ctx["door"].get_open_alpha())
            loc = pawn.get_actor_location()
            target = waypoints[wp_index]
            if v2(loc, target) < 45.0:
                wp_index += 1
                if wp_index >= len(waypoints):
                    state = "at_counter"
                    return
                target = waypoints[wp_index]
            if monotonic() - walk_start > 25.0:
                raise RuntimeError(f"player got stuck walking into the Apotheke at waypoint {wp_index}, loc={loc}")
            d = unreal.Vector(target.x - loc.x, target.y - loc.y, 0.0)
            pawn.add_movement_input(d / max(d.length(), 1.0), 1.0, False)
            return

        if state == "at_counter":
            it = ctx["apo"]
            loc = pawn.get_actor_location()
            if str(sub.find_interior_at_location(loc)) != str(it.get_editor_property("interior_id")):
                raise RuntimeError(f"player at the counter is not inside the Apotheke interior: {loc}")
            floor_z = it.get_editor_property("floor_z")
            if abs((loc.z - 90.0) - floor_z) > 25.0:
                raise RuntimeError(f"player stands {loc.z - floor_z:.1f} cm above the Apotheke floor")
            if door_max_alpha < 0.9:
                raise RuntimeError(f"Apotheke door never opened (max alpha {door_max_alpha:.2f})")
            interaction.refresh_nearest_entrance()
            if not interaction.has_interactable_entrance() or str(interaction.get_nearest_place_id()) != APOTHEKE:
                raise RuntimeError(f"counter prompt missing: place={interaction.get_nearest_place_id()}")
            if not interaction.try_interact() or not interaction.is_menu_open():
                raise RuntimeError("place menu did not open at the counter")
            money_before = econ.get_player_money_cents()
            if not econ.buy_item(APOTHEKE, "item_pflaster", 1):
                raise RuntimeError("buying at the Apotheke counter failed")
            interaction.close_menu()
            results["bought_cents"] = money_before - econ.get_player_money_cents()
            results["walk_s"] = round(monotonic() - walk_start, 1)
            state = "closed_door"
            ticks = 0
            return

        if state == "closed_door":
            # Sunday: closed. Outside the door the leaf stays shut and blocks, the HUD shows the opening time.
            sub.set_day_number(7)
            sub.set_time_of_day_minutes(600.0)
            door = ctx["door"]
            inward = door.get_editor_property("inward_direction")
            outside = ctx["apo"].get_editor_property("door_outside_location")
            if ticks == 0:
                pawn.set_actor_location(outside - inward * 60.0 + unreal.Vector(0, 0, 95.0), False, True)
                walk_start = monotonic()
            ticks += 1
            door.update_door_state(1.0)
            pawn.add_movement_input(inward, 1.0, False)
            if monotonic() - walk_start < 2.5:
                return
            if not door.is_fully_closed():
                raise RuntimeError("door opened for a closed place")
            center = door.get_editor_property("door_center")
            loc = pawn.get_actor_location()
            depth = (loc.x - center.x) * inward.x + (loc.y - center.y) * inward.y
            if depth > 0.0:
                raise RuntimeError(f"player walked through the closed door ({depth:.1f} cm inside)")
            interaction.refresh_nearest_entrance()
            prompt = interaction.get_interaction_prompt()
            if "geschlossen" not in prompt:
                raise RuntimeError(f"closed prompt missing at the door: {prompt!r}")
            results["closed_prompt"] = prompt
            state = "board"
            return

        if state == "board":
            sub.set_day_number(1)
            sub.set_time_of_day_minutes(600.0)
            it = interior(sub, RATHAUS)
            if not it.get_editor_property("has_notice_board"):
                raise RuntimeError("Bürgerbüro has no notice board")
            board = it.get_editor_property("notice_board_location")
            pawn.set_actor_location(board + unreal.Vector(0, 0, 95.0), False, True)
            interaction.refresh_nearest_entrance()
            if not interaction.has_interactable_notice_board():
                raise RuntimeError(f"no notice board prompt: {interaction.get_interaction_prompt()!r}")
            results["board_prompt"] = interaction.get_interaction_prompt()
            if not interaction.try_interact() or not interaction.is_task_board_open():
                raise RuntimeError("task board did not open")
            widget = interaction.get_active_task_board_widget()
            offers = widget.get_offer_count()
            if offers < 1:
                raise RuntimeError("notice board shows no offers")
            task_id = widget.get_offer_task_id(0)
            if not widget.accept_offer_at_index(0):
                raise RuntimeError("accepting the first offer failed")
            task = tsk.get_task_by_id(task_id)
            if task is None or task.get_editor_property("status") != unreal.DoemitzTaskStatus.ACTIVE:
                raise RuntimeError("accepted board task is not active")
            interaction.close_menu()
            results["board_offers"] = offers
            state = "citizens"
            return

        if state == "citizens":
            sub.set_day_number(1)
            sub.set_time_of_day_minutes(760.0)  # Monday 12:40, Kaufhaus open
            work = unreal.DoemitzCitizenActivity.WORKING
            shop = unreal.DoemitzCitizenActivity.SHOPPING
            placed = [("citizen_bernd_02", work), ("citizen_clara_03", work), ("citizen_anna_01", shop),
                      ("citizen_dieter_04", shop), ("altstadt_citizen_10", shop), ("altstadt_citizen_16", shop)]
            for cid, act in placed:
                if not cit.set_citizen_at_place_for_test(cid, KAUFHAUS, act):
                    raise RuntimeError(f"cannot place {cid}")
            it = interior(sub, KAUFHAUS)
            iid = str(it.get_editor_property("interior_id"))
            inside = []
            seen = set()
            for cid, _ in placed:
                res = cit.get_citizen_presentation_transform(cid)
                if res is None:
                    raise RuntimeError(f"no presentation transform for {cid}")
                loc = res[0]
                if str(sub.find_interior_at_location(loc)) == iid:
                    key = (round(loc.x), round(loc.y))
                    if key in seen:
                        raise RuntimeError(f"two citizens share a stand spot at {key}")
                    seen.add(key)
                    inside.append(cid)
            if not inside or "citizen_bernd_02" not in inside:
                raise RuntimeError(f"expected the Kaufhaus worker inside, got {inside}")
            if len(inside) > 6:
                raise RuntimeError(f"more than 6 visible citizens inside: {len(inside)}")
            results["citizens_inside"] = len(inside)
            # Save inside the Kaufhaus
            spot = it.get_editor_property("stand_spots")[-1].get_editor_property("location")
            room_pt = unreal.Vector((spot.x + it.get_editor_property("counter_location").x) * 0.5,
                                    (spot.y + it.get_editor_property("counter_location").y) * 0.5,
                                    it.get_editor_property("floor_z") + 92.0)
            pawn.set_actor_location(room_pt, False, True)
            ctx["save_pt"] = room_pt
            ctx["kaufhaus"] = it
            if not save.save_city_state(SLOT):
                raise RuntimeError("save inside the Kaufhaus failed")
            pawn.set_actor_location(room_pt + unreal.Vector(0, 0, 900.0), False, True)
            state = "load"
            return

        if state == "load":
            if not save.load_city_state(SLOT):
                raise RuntimeError("load failed")
            it = ctx["kaufhaus"]
            loc = pawn.get_actor_location()
            if str(save.get_last_loaded_player_interior_id()) != str(it.get_editor_property("interior_id")):
                raise RuntimeError(f"saved interior id not restored: {save.get_last_loaded_player_interior_id()}")
            if v2(loc, ctx["save_pt"]) > 5.0 or abs((loc.z - 92.0) - it.get_editor_property("floor_z")) > 15.0:
                raise RuntimeError(f"player not restored on the Kaufhaus floor: {loc}, floor {it.get_editor_property('floor_z')}")
            results["load_z_above_floor_cm"] = round(loc.z - it.get_editor_property("floor_z"), 1)
            finish(f"DOEMITZ_INTERIORS_PIE_OK: {results}", True)
            state = "done"
    except Exception:
        state = "done"
        finish("DOEMITZ_INTERIORS_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(tick)
level.editor_request_begin_play()
