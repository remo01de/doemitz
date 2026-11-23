from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
dn_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzDayNightController")
cfg_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzSimulationConfig")
deadline = monotonic() + 90
checked = False


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def check(_delta_seconds):
    global checked
    try:
        if checked:
            return
        if monotonic() > deadline:
            raise RuntimeError("timed out waiting for day/night and HUD")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        cit = unreal.DoemitzCitizenSubsystem.get(world)
        if sub is None or cit is None or cit.get_citizen_count() == 0:
            return

        dns = unreal.GameplayStatics.get_all_actors_of_class(world, dn_class)
        cfgs = unreal.GameplayStatics.get_all_actors_of_class(world, cfg_class)
        if len(dns) != 1 or len(cfgs) != 1:
            raise RuntimeError(f"expected 1 DayNightController and 1 SimulationConfig, got {len(dns)}/{len(cfgs)}")

        dn = dns[0]
        cfg = cfgs[0]
        widget = cfg.get_clock_widget()
        if widget is None:
            return

        # Test Noon (12:00 = 720 min)
        sub.set_time_of_day_minutes(720.0)
        dn.update_lighting_from_simulation()
        widget.refresh_display()
        noon_elev = dn.get_sun_elevation_degrees()
        noon_day = dn.is_daytime()
        noon_intensity = dn.get_current_sun_intensity()
        noon_lamps = dn.get_active_street_light_intensity()
        noon_clock = widget.get_clock_text_string()
        noon_status = widget.get_status_text_string()

        if not noon_day or noon_elev < 55.0 or noon_intensity < 3.0 or noon_lamps > 1.0:
            raise RuntimeError(f"unexpected noon lighting: elev={noon_elev}, intensity={noon_intensity}, lamps={noon_lamps}")
        expected_citizens = f"{cit.get_citizen_count()} Einwohner"
        if "12:00" not in noon_clock or "Mo, Tag 1" not in noon_clock or expected_citizens not in noon_status or "Grafik:" not in noon_status:
            raise RuntimeError(f"unexpected noon HUD: {noon_clock!r} / {noon_status!r}")

        # Test Midnight (00:00 = 0 min)
        sub.set_time_of_day_minutes(0.0)
        dn.update_lighting_from_simulation()
        widget.refresh_display()
        night_elev = dn.get_sun_elevation_degrees()
        night_day = dn.is_daytime()
        night_intensity = dn.get_current_sun_intensity()
        night_lamps = dn.get_active_street_light_intensity()
        night_clock = widget.get_clock_text_string()

        if night_day or night_elev > -50.0 or night_intensity > 0.5 or night_lamps < 3000.0:
            raise RuntimeError(f"unexpected night lighting: elev={night_elev}, intensity={night_intensity}, lamps={night_lamps}")
        if "00:00" not in night_clock:
            raise RuntimeError(f"unexpected night HUD: {night_clock!r}")

        checked = True
        finish(
            f"DOEMITZ_DAYNIGHT_HUD_PIE_OK: noon={noon_elev:.1f}deg/sun={noon_intensity:.2f}/lamps={noon_lamps:.0f} ({noon_clock}), "
            f"night={night_elev:.1f}deg/sun={night_intensity:.2f}/lamps={night_lamps:.0f} ({night_clock}), status='{noon_status}'",
            True,
        )
    except Exception:
        checked = True
        finish("DOEMITZ_DAYNIGHT_HUD_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
