import json
from math import hypot
from pathlib import Path
from time import monotonic
import traceback

import unreal

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
vehicle_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzTrafficVehicle")
project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
package = json.loads((project.parents[1] / "data/processed/doemitz-altstadt/unreal-city-meshes.json").read_text(encoding="utf-8"))

bridges_by_id = {b["id"]: b for b in package.get("bridges", [])}
torbruecke = bridges_by_id["bridge:osm:way:29732766"]
steinbruecke = bridges_by_id["bridge:osm:way:94526517"]
flauten_steg = bridges_by_id["bridge:osm:way:29732751"]
nw_steg = bridges_by_id["bridge:osm:way:120432334"]
nw_tunnel = next(
    p for p in package.get("tunnel_portals", [])
    if p["road_id"] == "osm:way:416256369"
)

stein_edge = next(
    e for e in package["road-graph"]["edges"]
    if e["way_id"] == "osm:way:94526517" and e["id"].endswith(":fwd")
)


def ue_pos(pt):
    return unreal.Vector(pt[1] * 100.0, pt[0] * 100.0, pt[2] * 100.0)


def linear_bridge_z_cm(bridge, ue_x, ue_y):
    a = ue_pos(bridge["abutments"][0]["position_m"])
    b = ue_pos(bridge["abutments"][1]["position_m"])
    dx, dy = b.x - a.x, b.y - a.y
    len_sq = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((ue_x - a.x) * dx + (ue_y - a.y) * dy) / max(len_sq, 1.0)))
    return a.z + t * (b.z - a.z)


deadline = monotonic() + 110
phase = "init"
tor_a = ue_pos(torbruecke["abutments"][0]["position_m"])
tor_b = ue_pos(torbruecke["abutments"][1]["position_m"])
nw_a = ue_pos(nw_steg["abutments"][0]["position_m"])
nw_portal = ue_pos(nw_tunnel["entry_point_3d_m"])
nw_exit = ue_pos(nw_tunnel["exit_point_3d_m"])
walk_steps = 0
max_player_dev_cm = 0.0
nw_tunnel_max_dev_cm = 0.0
capsule_half_h = 90.0
stein_max_dip_cm = 0.0
steg_max_dev_cm = 0.0
save_bridge_dev_cm = 0.0
slot_name = "DoemitzVerifyBridgeSave"


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    if unreal.GameplayStatics.does_save_game_exist(slot_name, 0):
        unreal.GameplayStatics.delete_game_in_slot(slot_name, 0)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def trace_ground(world, x, y, ignore):
    hit = unreal.SystemLibrary.line_trace_single(
        world,
        unreal.Vector(x, y, 5000.0),
        unreal.Vector(x, y, -5000.0),
        unreal.TraceTypeQuery.ECC_VISIBILITY,
        False,
        ignore,
        unreal.DrawDebugTrace.NONE,
        False,
    )
    return hit.to_dict()["impact_point"].z if hit is not None else None


def get_cstate(sub, cid):
    res = sub.get_citizen_state(cid)
    return res[1] if isinstance(res, tuple) else res


def tick(_delta_seconds):
    global phase, walk_steps, max_player_dev_cm, nw_tunnel_max_dev_cm, capsule_half_h
    global stein_max_dip_cm, steg_max_dev_cm, save_bridge_dev_cm
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during phase={phase} (steps={walk_steps})")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if sub is None or pawn is None or sub.get_citizen_count() == 0:
            return

        if phase == "init":
            if not pawn.get_editor_property("character_movement").is_moving_on_ground():
                return
            cap = pawn.get_component_by_class(unreal.CapsuleComponent)
            if cap is not None:
                capsule_half_h = float(cap.get_scaled_capsule_half_height())

            # Verify SM_Bridges actor exists in world with BlockAll collision
            bridge_actor = None
            for act in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor):
                if act.get_actor_label() == "Altstadt Bridges":
                    bridge_actor = act
                    break
            if bridge_actor is None:
                raise RuntimeError("Altstadt Bridges actor not found in level")

            vehicles = unreal.GameplayStatics.get_all_actors_of_class(world, vehicle_class)
            if not vehicles:
                raise RuntimeError("No vehicles spawned")
            car = next((v for v in vehicles if str(v.get_vehicle_id()) == "altstadt_vehicle_01"), vehicles[0])
            ignore = [pawn, *vehicles]

            # 1. Vehicle crosses Steinbrücke (16.4 m) without any dip
            stein_len_cm = stein_edge["length_m"] * 100.0
            for step in range(9):
                d_cm = min(stein_len_cm - 25.0, max(25.0, (step / 8.0) * stein_len_cm))
                sub.set_vehicle_edge_position_for_test(car.get_vehicle_id(), stein_edge["id"], d_cm, 400.0)
                car.sync_from_simulation()
                vloc = car.get_actor_location()
                exp_z = linear_bridge_z_cm(steinbruecke, vloc.x, vloc.y)
                dip = abs(vloc.z - exp_z)
                stein_max_dip_cm = max(stein_max_dip_cm, dip)
                if dip > 4.0:
                    raise RuntimeError(
                        f"Vehicle on Steinbrücke dipped at d={d_cm:.1f}cm: z={vloc.z:.1f} vs linear={exp_z:.1f}"
                    )
                gz = trace_ground(world, vloc.x, vloc.y, ignore)
                if gz is None or abs(gz - exp_z) > 6.0:
                    raise RuntimeError(
                        f"Steinbrücke deck collision mismatch at d={d_cm:.1f}cm: hit={gz} vs linear={exp_z:.1f}"
                    )

            # 2. Citizen crosses Fläutendörper Steg (36.8 m) cleanly on the linear wooden deck
            steg_a = ue_pos(flauten_steg["abutments"][0]["position_m"])
            steg_b = ue_pos(flauten_steg["abutments"][1]["position_m"])
            for step in range(11):
                t = step / 10.0
                sx = steg_a.x + (steg_b.x - steg_a.x) * t
                sy = steg_a.y + (steg_b.y - steg_a.y) * t
                exp_z = steg_a.z + (steg_b.z - steg_a.z) * t
                gz = trace_ground(world, sx, sy, ignore)
                if gz is None:
                    raise RuntimeError(f"Fläutendörper Steg collision missed at t={t:.2f}")
                dev = abs(gz - exp_z)
                steg_max_dev_cm = max(steg_max_dev_cm, dev)
                if dev > 5.0:
                    raise RuntimeError(
                        f"Fläutendörper Steg height deviation {dev:.2f}cm at t={t:.2f}: hit={gz:.1f} vs linear={exp_z:.1f}"
                    )
                sub.set_citizen_position_for_test("citizen_anna_01", unreal.Vector(sx, sy, gz))
                anna_loc = get_cstate(sub, "citizen_anna_01").get_editor_property("world_location")
                if abs(anna_loc.z - exp_z) > 5.0:
                    raise RuntimeError(f"Citizen on Fläutendörper Steg off deck: {anna_loc.z:.1f} vs {exp_z:.1f}")

            # 3. SaveGame with position on Torbrücke (including low/pre-11.1 Z) loads ON TOP of the bridge deck, never in moat!
            mid_x = 0.5 * (tor_a.x + tor_b.x)
            mid_y = 0.5 * (tor_a.y + tor_b.y)
            mid_exp_z = linear_bridge_z_cm(torbruecke, mid_x, mid_y)
            # Simulate a pre-11.1/v5 sunken save coordinate on Torbrücke (Z=120 cm down in canal)
            pawn.set_actor_location(unreal.Vector(mid_x, mid_y, 120.0), False, True)
            sub.set_citizen_position_for_test("citizen_anna_01", unreal.Vector(mid_x, mid_y, 120.0))
            if not sub.save_city_state(slot_name):
                raise RuntimeError("SaveCityState failed on bridge save test")
            if not sub.load_city_state(slot_name):
                raise RuntimeError("LoadCityState failed on bridge save test")
            restored_p = pawn.get_actor_location()
            restored_c = get_cstate(sub, "citizen_anna_01").get_editor_property("world_location")
            p_feet = restored_p.z - capsule_half_h
            save_bridge_dev_cm = max(abs(p_feet - mid_exp_z), abs(restored_c.z - mid_exp_z))
            if save_bridge_dev_cm > 12.0:
                raise RuntimeError(
                    f"Bridge SaveGame load landed off deck: player_feet={p_feet:.1f}cm, citizen={restored_c.z:.1f}cm, "
                    f"expected_deck={mid_exp_z:.1f}cm"
                )

            # 4. Place player on Torbrücke abutment A (2 m inside bridge) and walk across to abutment B
            dx, dy = tor_b.x - tor_a.x, tor_b.y - tor_a.y
            norm = hypot(dx, dy)
            start_x = tor_a.x + (dx / norm) * 150.0
            start_y = tor_a.y + (dy / norm) * 150.0
            start_z = linear_bridge_z_cm(torbruecke, start_x, start_y)
            pawn.set_actor_location(unreal.Vector(start_x, start_y, start_z + capsule_half_h + 2.0), False, True)
            walk_steps = 0
            max_player_dev_cm = 0.0
            phase = "walk_torbruecke"
            return

        if phase == "walk_torbruecke":
            pos = pawn.get_actor_location()
            dx, dy = tor_b.x - tor_a.x, tor_b.y - tor_a.y
            norm = hypot(dx, dy)
            end_x = tor_b.x - (dx / norm) * 150.0
            end_y = tor_b.y - (dy / norm) * 150.0

            if walk_steps >= 3 and pawn.get_editor_property("character_movement").is_moving_on_ground():
                exp_z = linear_bridge_z_cm(torbruecke, pos.x, pos.y)
                feet_z = pos.z - capsule_half_h
                dev = abs(feet_z - exp_z)
                max_player_dev_cm = max(max_player_dev_cm, dev)
                if dev > 5.0:
                    raise RuntimeError(
                        f"Player on Torbrücke deviated {dev:.2f} cm (>5 cm) from linear profile: "
                        f"feet_z={feet_z:.1f} vs linear={exp_z:.1f} at ({pos.x:.0f},{pos.y:.0f})"
                    )

            delta = unreal.Vector(end_x - pos.x, end_y - pos.y, 0.0)
            dist_2d = delta.length()
            if dist_2d > 80.0:
                pawn.add_movement_input(delta / dist_2d, 1.0, False)
                walk_steps += 1
                return

            # 5. Place player on NW-Steg (6 m before eastern tunnel portal) and walk straight into the tunnel
            dx_b, dy_b = nw_portal.x - nw_a.x, nw_portal.y - nw_a.y
            norm_b = hypot(dx_b, dy_b)
            nw_start_x = nw_portal.x - (dx_b / norm_b) * 600.0
            nw_start_y = nw_portal.y - (dy_b / norm_b) * 600.0
            nw_start_z = linear_bridge_z_cm(nw_steg, nw_start_x, nw_start_y)
            pawn.set_actor_location(unreal.Vector(nw_start_x, nw_start_y, nw_start_z + capsule_half_h + 2.0), False, True)
            walk_steps = 0
            nw_tunnel_max_dev_cm = 0.0
            phase = "walk_nw_steg_tunnel"
            return

        if phase == "walk_nw_steg_tunnel":
            pos = pawn.get_actor_location()
            dx_t, dy_t = nw_exit.x - nw_portal.x, nw_exit.y - nw_portal.y
            norm_t = max(hypot(dx_t, dy_t), 1.0)
            target_x = nw_portal.x + (dx_t / norm_t) * 700.0
            target_y = nw_portal.y + (dy_t / norm_t) * 700.0

            if walk_steps >= 3 and pawn.get_editor_property("character_movement").is_moving_on_ground():
                # Project onto tunnel if past portal, else onto NW-Steg bridge
                proj_t = ((pos.x - nw_portal.x) * dx_t + (pos.y - nw_portal.y) * dy_t) / (norm_t * norm_t)
                if proj_t >= 0.0:
                    t_clamped = min(1.0, proj_t)
                    exp_z = nw_portal.z + t_clamped * (nw_exit.z - nw_portal.z)
                else:
                    exp_z = linear_bridge_z_cm(nw_steg, pos.x, pos.y)
                feet_z = pos.z - capsule_half_h
                dev = abs(feet_z - exp_z)
                nw_tunnel_max_dev_cm = max(nw_tunnel_max_dev_cm, dev)
                if dev > 5.0:
                    raise RuntimeError(
                        f"Player on NW-Steg->Tunnel jumped {dev:.2f} cm (>5 cm): "
                        f"feet_z={feet_z:.1f} vs expected={exp_z:.1f} at ({pos.x:.0f},{pos.y:.0f})"
                    )

            delta = unreal.Vector(target_x - pos.x, target_y - pos.y, 0.0)
            dist_2d = delta.length()
            if dist_2d > 80.0:
                pawn.add_movement_input(delta / dist_2d, 1.0, False)
                walk_steps += 1
                return

            phase = "done"
            finish(
                f"DOEMITZ_BRIDGES_PIE_OK: Torbrücke walked (max_dev={max_player_dev_cm:.2f}cm<=5cm), "
                f"NW-Steg->Tunnel walked (max_dev={nw_tunnel_max_dev_cm:.2f}cm<=5cm), "
                f"Steinbrücke vehicle (max_dip={stein_max_dip_cm:.2f}cm), "
                f"Fläutendörper Steg citizen (max_dev={steg_max_dev_cm:.2f}cm), "
                f"bridge SaveGame reload (dev={save_bridge_dev_cm:.2f}cm) verified",
                True,
            )
    except Exception:
        phase = "done"
        finish("DOEMITZ_BRIDGES_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(tick)
level.editor_request_begin_play()
