"""Sprint 15 PIE verification:
- 6 domain UWorldSubsystems active & wired
- Hybrid time scale (BaseTimeScale=20.0, HUD labels 1x/5x/15x/Pause, visible walking pace vs off-screen catch-up)
- Mid-trip schedule change continues smoothly from current WorldLocation (no teleport back to CurrentPlaceId)
- DoemitzLow throttles street lights ONLY and leaves all interior ceiling lights visible & unhidden
"""

from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
cfg_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzSimulationConfig")
dn_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzDayNightController")
deadline = monotonic() + 100

phase = "init"
vis_start_loc = None
vis_start_time = 0.0
vis_speed_cm_s = 0.0
mid_before_loc = None
mid_jump_cm = 0.0
off_start_loc = None
off_start_time = 0.0
off_speed_cm_s = 0.0
interior_light_count = 0
street_lights_hidden = 0


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def get_cstate(cit, cid):
    res = cit.get_citizen_state(cid)
    return res[1] if isinstance(res, tuple) else res


def check(_delta_seconds):
    global phase, vis_start_loc, vis_start_time, vis_speed_cm_s
    global mid_before_loc, mid_jump_cm, off_start_loc, off_start_time, off_speed_cm_s
    global interior_light_count, street_lights_hidden
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during phase={phase}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return

        sim = unreal.DoemitzSimulationSubsystem.get(world)
        econ = unreal.DoemitzEconomySubsystem.get(world)
        cit = unreal.DoemitzCitizenSubsystem.get(world)
        trf = unreal.DoemitzTrafficSubsystem.get(world)
        tsk = unreal.DoemitzTaskSubsystem.get(world)
        save = unreal.DoemitzSaveSubsystem.get(world)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        cfgs = unreal.GameplayStatics.get_all_actors_of_class(world, cfg_class)
        dns = unreal.GameplayStatics.get_all_actors_of_class(world, dn_class)
        if (
            sim is None or econ is None or cit is None or trf is None or tsk is None or save is None
            or pawn is None or len(cfgs) != 1 or len(dns) != 1 or cit.get_citizen_count() < 30
        ):
            return
        widget = cfgs[0].get_clock_widget()
        if widget is None:
            return

        if phase == "init":
            # 1. Verify BaseTimeScale == 20.0 and relative HUD labels (1x/5x/15x/Pause) + updated status title
            base_scale = sim.get_base_time_scale()
            if abs(base_scale - 20.0) > 0.01:
                raise RuntimeError(f"expected BaseTimeScale=20.0, got {base_scale}")

            for scale_val, expected_tag in (
                (base_scale, "(1x)"),
                (base_scale * 5.0, "(5x)"),
                (base_scale * 15.0, "(15x)"),
                (0.0, "(Pause)"),
            ):
                sim.set_time_scale(scale_val)
                widget.refresh_display()
                clk = widget.get_clock_text_string()
                if expected_tag not in clk:
                    raise RuntimeError(f"expected {expected_tag} in clock HUD at scale={scale_val}, got {clk!r}")

            status_str = widget.get_status_text_string()
            if "D\u00f6mitz Altstadt" in status_str or "D\u00f6mitz  |" not in status_str:
                raise RuntimeError(f"expected updated city title 'Dömitz  |' in status HUD, got {status_str!r}")

            # 2. Verify M4 lighting fix: DoemitzLow leaves all interior ceiling lights visible while still throttling street lamps
            gfx = unreal.DoemitzGraphicsSettings.get()
            if gfx is None or gfx.get_active_profile_name() != "DoemitzLow":
                raise RuntimeError(f"expected DoemitzLow default profile, got {gfx.get_active_profile_name() if gfx else None}")

            all_point_lights = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.PointLight)
            interior_lights = [a for a in all_point_lights if a.get_actor_label().startswith("Altstadt InteriorLight ")]
            street_lights = [a for a in all_point_lights if a.get_actor_label().startswith("Altstadt StreetLight")]
            if len(interior_lights) < 18:
                raise RuntimeError(f"expected >=18 interior ceiling lights, found {len(interior_lights)}")
            for lamp in interior_lights:
                comp = lamp.get_component_by_class(unreal.PointLightComponent)
                if lamp.get_editor_property("hidden") or comp is None or not comp.is_visible():
                    raise RuntimeError(f"interior light {lamp.get_actor_label()} was hidden/disabled under DoemitzLow!")
            interior_light_count = len(interior_lights)
            street_lights_hidden = sum(1 for a in street_lights if a.get_editor_property("hidden"))
            if street_lights and street_lights_hidden == 0:
                raise RuntimeError("expected DoemitzLow to throttle a portion of street lights, got 0 hidden")

            # 3. Start Anna's morning commute (07:55) with player right beside her (< 150 m -> visible walking pace)
            sim.set_day_number(1)
            sim.set_time_of_day_minutes(475.0)
            sim.set_time_scale(base_scale)
            unreal.GameplayStatics.set_global_time_dilation(world, 1.0)
            anna = get_cstate(cit, "citizen_anna_01")
            anna_loc = anna.get_editor_property("world_location")
            pawn.set_actor_location(anna_loc + unreal.Vector(250.0, 0.0, 100.0), False, True)
            phase = "wait_visible_move"
            return

        if phase == "wait_visible_move":
            anna = get_cstate(cit, "citizen_anna_01")
            if not anna.get_editor_property("is_moving") or not cit.is_citizen_high_detail("citizen_anna_01"):
                return
            if anna.get_editor_property("route_progress_cm") < 50.0:
                return
            vis_start_loc = anna.get_editor_property("world_location")
            vis_start_time = monotonic()
            phase = "measure_visible_speed"
            return

        if phase == "measure_visible_speed":
            elapsed = monotonic() - vis_start_time
            if elapsed < 1.2:
                return
            anna = get_cstate(cit, "citizen_anna_01")
            cur_loc = anna.get_editor_property("world_location")
            dist_cm = (cur_loc - vis_start_loc).length()
            vis_speed_cm_s = dist_cm / max(elapsed, 0.01)
            # Normal walking pace is ~135 cm/s (allow generous PIE frame jitter 50..350 cm/s, well below 2700 cm/s game-time)
            if not (50.0 <= vis_speed_cm_s <= 350.0):
                raise RuntimeError(
                    f"visible citizen walked at {vis_speed_cm_s:.1f} cm/s (expected ~135 cm/s normal pace, dist={dist_cm:.1f}cm in {elapsed:.2f}s)"
                )

            # 4. Mid-trip continuity: while Anna is moving mid-street, switch schedule to 12:30 Shopping (place_kaufhaus)
            # She must continue smoothly from cur_loc without teleporting back to CurrentPlaceId!
            mid_before_loc = cur_loc
            sim.set_time_of_day_minutes(750.0)
            phase = "verify_midtrip_continuity"
            return

        if phase == "verify_midtrip_continuity":
            anna = get_cstate(cit, "citizen_anna_01")
            target = str(anna.get_editor_property("target_place_id"))
            if target != "place_kaufhaus":
                return
            after_loc = anna.get_editor_property("world_location")
            mid_jump_cm = (after_loc - mid_before_loc).length()
            if not anna.get_editor_property("is_moving"):
                raise RuntimeError("Anna stopped moving on mid-trip target switch")
            if mid_jump_cm > 350.0:
                raise RuntimeError(
                    f"Mid-trip StartTrip teleported Anna by {mid_jump_cm:.1f} cm (before={mid_before_loc}, after={after_loc})"
                )

            # 5. Off-screen game-time catch-up: teleport player > 150 m away from Bernd at 08:00 commute (1x = 20.0)
            sim.set_time_of_day_minutes(480.0)
            sim.set_time_scale(sim.get_base_time_scale())
            unreal.GameplayStatics.set_global_time_dilation(world, 2.0)
            bernd = get_cstate(cit, "citizen_bernd_02")
            bernd_loc = bernd.get_editor_property("world_location")
            pawn.set_actor_location(bernd_loc + unreal.Vector(40000.0, 40000.0, 200.0), False, True)
            off_start_loc = bernd_loc
            off_start_time = monotonic()
            phase = "verify_offscreen_speed"
            return

        if phase == "verify_offscreen_speed":
            if cit.is_citizen_high_detail("citizen_bernd_02"):
                return
            bernd = get_cstate(cit, "citizen_bernd_02")
            cur_loc = bernd.get_editor_property("world_location")
            dist_cm = (cur_loc - off_start_loc).length()
            elapsed = monotonic() - off_start_time
            if dist_cm < 1200.0:
                if elapsed > 6.0:
                    raise RuntimeError(
                        f"off-screen citizen did not advance in game time (moved only {dist_cm:.1f} cm in {elapsed:.2f}s)"
                    )
                return
            off_speed_cm_s = dist_cm / max(elapsed, 0.01)
            # At TimeScale=20.0 and dilation=2.0, off-screen travel advances at ~5400 cm/s (much faster than visible ~135 cm/s!)
            if off_speed_cm_s < vis_speed_cm_s * 3.0:
                raise RuntimeError(
                    f"off-screen speed ({off_speed_cm_s:.1f} cm/s) not significantly faster than visible ({vis_speed_cm_s:.1f} cm/s)"
                )

            phase = "done"
            finish(
                f"DOEMITZ_SPRINT15_PIE_OK: 6 subsystems active, BaseTimeScale=20.0 (HUD 1x/5x/15x/Pause OK), "
                f"visible_speed={vis_speed_cm_s:.1f}cm/s, offscreen_speed={off_speed_cm_s:.1f}cm/s, "
                f"midtrip_jump={mid_jump_cm:.1f}cm, interior_lights_visible={interior_light_count} "
                f"(street_lights_hidden_low={street_lights_hidden})",
                True,
            )
    except Exception:
        phase = "done"
        finish("DOEMITZ_SPRINT15_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
