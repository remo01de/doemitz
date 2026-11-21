import json
from pathlib import Path
from time import monotonic
import traceback

import unreal

level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
vehicle_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzTrafficVehicle")
project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
package = json.loads((project.parents[1] / "data/processed/doemitz-altstadt/unreal-city-meshes.json").read_text(encoding="utf-8"))

# Pick a real sloped drivable edge in main SCC for vehicle pitch & contact verification
sloped_edge = None
best_dz = 0.0
for edge in package["road-graph"]["edges"]:
    if edge.get("dead_end") or edge.get("length_m", 0.0) < 12.0:
        continue
    pts = edge["points_m"]
    dz = max(abs(b[2] - a[2]) for a, b in zip(pts, pts[1:]))
    total_dz = abs(pts[-1][2] - pts[0][2])
    if total_dz > best_dz and dz > 0.05:
        best_dz = total_dz
        sloped_edge = edge

deadline = monotonic() + 110
phase = "init"
walk_waypoints = []
wp_idx = 0
min_walk_z = 1e9
max_walk_z = -1e9
walk_steps = 0
vehicle_checked_pitch = 0.0
vehicle_checked_gap = 0.0
offpool_citizen_id = ""
offpool_z_diff = 0.0


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def trace_ground_z(world, x, y, ignore_actors):
    hit = unreal.SystemLibrary.line_trace_single(
        world,
        unreal.Vector(x, y, 5000.0),
        unreal.Vector(x, y, -5000.0),
        unreal.TraceTypeQuery.ECC_VISIBILITY,
        False,
        ignore_actors,
        unreal.DrawDebugTrace.NONE,
        False,
    )
    if hit is None:
        return None
    return hit.to_dict()["impact_point"].z


def get_cstate(sub, cid):
    res = sub.get_citizen_state(cid)
    return res[1] if isinstance(res, tuple) else res


def get_vstate(sub, vid):
    res = sub.get_vehicle_state(vid)
    return res[1] if isinstance(res, tuple) else res


def tick(_delta_seconds):
    global phase, walk_waypoints, wp_idx, min_walk_z, max_walk_z, walk_steps
    global vehicle_checked_pitch, vehicle_checked_gap, offpool_citizen_id, offpool_z_diff
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during phase={phase} (wp={wp_idx}/{len(walk_waypoints)})")
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

            # 1. Verify in-game TextRenderActor shows GeoBasis-DE/M-V alongside OpenStreetMap
            found_attr = False
            seen_texts = []
            for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.TextRenderActor):
                comp = actor.get_component_by_class(unreal.TextRenderComponent)
                if comp is not None:
                    txt = str(comp.get_editor_property("text"))
                    seen_texts.append(txt)
                    if "OpenStreetMap" in txt and "GeoBasis-DE/M-V" in txt:
                        found_attr = True
                        break
            if not found_attr:
                raise RuntimeError(f"In-game TextRenderActor missing OpenStreetMap + GeoBasis-DE/M-V attribution (seen={seen_texts!r})")

            # 2. Verify vehicle on sloped edge has non-zero pitch and stays grounded (no lift-off / clipping)
            if sloped_edge is None:
                raise RuntimeError("No sloped drivable edge found in road graph")
            vehicles = unreal.GameplayStatics.get_all_actors_of_class(world, vehicle_class)
            if not vehicles:
                raise RuntimeError("No traffic vehicles spawned")
            car = next((v for v in vehicles if str(v.get_vehicle_id()) == "altstadt_vehicle_01"), vehicles[0])
            edge_id = sloped_edge["id"]
            # Find steepest segment along sloped_edge and place vehicle at its midpoint
            pts = sloped_edge["points_m"]
            best_seg_s = 500.0
            best_seg_slope = 0.0
            cum = 0.0
            for a, b in zip(pts, pts[1:]):
                dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
                seg_m = (dx * dx + dy * dy + dz * dz) ** 0.5
                if seg_m > 0.5:
                    sl = abs(dz) / seg_m
                    if sl > best_seg_slope:
                        best_seg_slope = sl
                        best_seg_s = (cum + seg_m * 0.5) * 100.0
                cum += seg_m
            sub.set_vehicle_edge_position_for_test(car.get_vehicle_id(), edge_id, best_seg_s, 400.0)
            car.sync_from_simulation()
            vstate = get_vstate(sub, car.get_vehicle_id())
            vloc = car.get_actor_location()
            vrot = car.get_actor_rotation()
            vehicle_checked_pitch = abs(vrot.pitch)
            if vehicle_checked_pitch < 0.35:
                raise RuntimeError(
                    f"Vehicle on sloped edge {edge_id} has near-zero pitch={vrot.pitch:.3f} deg"
                )
            ignore = [pawn, *vehicles]
            gz = trace_ground_z(world, vloc.x, vloc.y, ignore)
            if gz is None:
                raise RuntimeError(f"Downward trace under vehicle on {edge_id} missed road surface")
            vehicle_checked_gap = abs(vloc.z - gz)
            if vehicle_checked_gap > 15.0:
                raise RuntimeError(
                    f"Vehicle lifted/clipped on sloped edge {edge_id}: vloc.z={vloc.z:.1f} vs ground={gz:.1f} (gap={vehicle_checked_gap:.1f} cm)"
                )

            # 3. Verify off-pool citizen (no active actor) appears at real terrain height when brought into LOD
            sub.set_citizen_lod_radius_cm(1200.0)
            far_cid = None
            for cid in sub.get_all_citizen_ids():
                if not sub.is_citizen_high_detail(cid):
                    far_cid = cid
                    break
            if far_cid is None:
                raise RuntimeError("Could not find off-pool citizen for terrain height check")
            offpool_citizen_id = str(far_cid)
            sim_loc = get_cstate(sub, far_cid).get_editor_property("world_location")
            cit_gz = trace_ground_z(world, sim_loc.x, sim_loc.y, ignore)
            if cit_gz is None:
                raise RuntimeError(f"Ground trace under off-pool citizen {far_cid} missed")
            # Now expand LOD radius so this citizen acquires a pooled Actor and check its Z
            sub.set_citizen_lod_radius_cm(120000.0)
            act_res = sub.get_citizen_actor_location(far_cid)
            has_act, act_loc = act_res if isinstance(act_res, tuple) else (True, act_res)
            if not has_act:
                raise RuntimeError(f"Off-pool citizen {far_cid} did not acquire an actor after expanding LOD radius")
            offpool_z_diff = abs(act_loc.z - cit_gz)
            if offpool_z_diff > 35.0:
                raise RuntimeError(
                    f"Off-pool citizen {far_cid} spawned off terrain: actor_z={act_loc.z:.1f} vs ground_z={cit_gz:.1f}"
                )
            sub.set_citizen_lod_radius_cm(15000.0)

            # 4. Walk player on Goethestrasse, then up the real OSM Festungswall ramp (osm:way:416326354: 3.61m -> 7.22m!)
            p0 = pawn.get_actor_location()
            walk_waypoints = [
                unreal.Vector(p0.x + 500.0, p0.y + 500.0, p0.z),
                unreal.Vector(-5573.0, -20370.0, 361.0),
                unreal.Vector(-5192.0, -20628.0, 363.0),
                unreal.Vector(-5044.0, -20864.0, 377.0),
                unreal.Vector(-5057.0, -21161.0, 400.0),
                unreal.Vector(-5197.0, -21546.0, 449.0),
                unreal.Vector(-6702.0, -23118.0, 709.0),
                unreal.Vector(-7538.0, -23332.0, 722.0),
            ]
            wp_idx = 0
            min_walk_z = p0.z
            max_walk_z = p0.z
            phase = "walk_goethe"
            return

        if phase == "walk_goethe":
            pos = pawn.get_actor_location()
            min_walk_z = min(min_walk_z, pos.z)
            max_walk_z = max(max_walk_z, pos.z)
            if pos.z < -300.0:
                raise RuntimeError(f"Player fell through terrain at {pos}")
            target = walk_waypoints[0]
            delta = unreal.Vector(target.x - pos.x, target.y - pos.y, 0.0)
            dist_2d = delta.length()
            if dist_2d > 45.0 and walk_steps < 120:
                pawn.add_movement_input(delta / dist_2d, 1.0, False)
                walk_steps += 1
                return
            # Step onto bottom of the Festungswall ramp (snapped to real ground) and walk up all 6 ramp segments!
            ramp_start = walk_waypoints[1]
            gz = trace_ground_z(world, ramp_start.x, ramp_start.y, [pawn])
            if gz is None:
                raise RuntimeError("Ground trace at Festungswall ramp start missed")
            pawn.set_actor_location(unreal.Vector(ramp_start.x, ramp_start.y, gz + 105.0), False, True)
            wp_idx = 2
            min_walk_z = gz + 105.0
            max_walk_z = gz + 105.0
            walk_steps = 0
            phase = "walk_festungswall"
            return

        if phase == "walk_festungswall":
            pos = pawn.get_actor_location()
            if pos.z < -300.0:
                raise RuntimeError(f"Player fell through Festungswall terrain at {pos}")
            if pawn.get_editor_property("character_movement").is_moving_on_ground():
                min_walk_z = min(min_walk_z, pos.z)
                max_walk_z = max(max_walk_z, pos.z)
            if wp_idx < len(walk_waypoints) and walk_steps < 600:
                target = walk_waypoints[wp_idx]
                delta = unreal.Vector(target.x - pos.x, target.y - pos.y, 0.0)
                dist_2d = delta.length()
                if dist_2d <= 95.0:
                    wp_idx += 1
                    return
                pawn.add_movement_input(delta / dist_2d, 1.0, False)
                walk_steps += 1
                return
            if not pawn.get_editor_property("character_movement").is_moving_on_ground():
                if walk_steps < 630:
                    walk_steps += 1
                    return
                raise RuntimeError(f"Player not grounded on Festungswall at {pos}")
            if max_walk_z - min_walk_z < 200.0:
                raise RuntimeError(
                    f"Expected >= 200 cm real terrain climb toward Festungswall, got {max_walk_z - min_walk_z:.1f} cm "
                    f"(min_z={min_walk_z:.1f}, max_z={max_walk_z:.1f}, wp={wp_idx}/{len(walk_waypoints)}, pos={pos})"
                )
            phase = "done"
            finish(
                f"DOEMITZ_TERRAIN_PIE_OK: walk_z=[{min_walk_z:.1f}, {max_walk_z:.1f}]cm (climb={max_walk_z - min_walk_z:.1f}cm), "
                f"vehicle_pitch={vehicle_checked_pitch:.2f}deg gap={vehicle_checked_gap:.1f}cm, "
                f"offpool_citizen={offpool_citizen_id} dz={offpool_z_diff:.1f}cm, GeoBasis attribution OK",
                True,
            )
    except Exception:
        phase = "done"
        finish("DOEMITZ_TERRAIN_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(tick)
level.editor_request_begin_play()
