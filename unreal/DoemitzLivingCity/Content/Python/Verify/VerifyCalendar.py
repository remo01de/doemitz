from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
cfg_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzSimulationConfig")
deadline = monotonic() + 90
phase = "check_initial"


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def get_state(sub, cid):
    res = sub.get_citizen_state(cid)
    return res[1] if isinstance(res, tuple) else res


def check(_delta_seconds):
    global phase
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during {phase}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        if sub is None or sub.get_citizen_count() < 30:
            return
        cfgs = unreal.GameplayStatics.get_all_actors_of_class(world, cfg_class)
        if len(cfgs) != 1:
            return
        widget = cfgs[0].get_clock_widget()
        if widget is None:
            return

        if phase == "check_initial":
            if sub.get_day_of_week() != 0 or sub.get_day_of_week_short_name() != "Mo" or sub.get_calendar_week() != 1:
                raise RuntimeError(
                    f"expected initial Monday KW 1, got dow={sub.get_day_of_week()} ({sub.get_day_of_week_short_name()}) KW={sub.get_calendar_week()}"
                )
            gfx = unreal.DoemitzGraphicsSettings.get()
            if gfx is None or gfx.get_active_profile_name() != "DoemitzLow":
                raise RuntimeError(f"expected default DoemitzLow profile, got {gfx.get_active_profile_name() if gfx else None}")
            widget.refresh_display()
            clock_str = widget.get_clock_text_string()
            status_str = widget.get_status_text_string()
            if "Mo, Tag 1" not in clock_str:
                raise RuntimeError(f"clock HUD missing 'Mo, Tag 1': {clock_str!r}")
            if "Grafik: Low" not in status_str:
                raise RuntimeError(f"status HUD missing 'Grafik: Low': {status_str!r}")

            # Verify midnight rollover Monday -> Tuesday
            sub.set_time_of_day_minutes(1439.5)
            sub.set_time_scale(600.0)
            unreal.GameplayStatics.set_global_time_dilation(world, 4.0)
            phase = "wait_rollover"
            return

        if phase == "wait_rollover":
            if sub.get_day_number() < 2:
                return
            if sub.get_day_of_week() != 1 or sub.get_day_of_week_short_name() != "Di":
                raise RuntimeError(
                    f"expected Tuesday after rollover, got dow={sub.get_day_of_week()} ({sub.get_day_of_week_short_name()})"
                )

            # Switch to Sunday (Day 7, So) at 10:00 (600 min): Kaufhaus is closed on Sunday.
            # Anna's Sunday schedule has Shopping at place_kaufhaus at 600 -> must skip to next activity (place_amtsverwaltung).
            sub.set_day_number(7)
            sub.set_time_of_day_minutes(600.0)
            sub.set_time_scale(60.0)
            unreal.GameplayStatics.set_global_time_dilation(world, 2.0)
            if sub.is_place_open_now("place_kaufhaus"):
                raise RuntimeError("expected place_kaufhaus to be closed on Sunday at 10:00")
            if not sub.is_place_open("place_kaufhaus", 0, 600.0):
                raise RuntimeError("expected place_kaufhaus to be open on Monday at 10:00")
            phase = "verify_closed_skip"
            return

        if phase == "verify_closed_skip":
            anna = get_state(sub, "citizen_anna_01")
            target = str(anna.get_editor_property("target_place_id"))
            if target == "place_kaufhaus":
                raise RuntimeError("Anna targeted closed shop place_kaufhaus on Sunday!")
            if target != "place_amtsverwaltung":
                return

            widget.refresh_display()
            sunday_clock = widget.get_clock_text_string()
            if "So, Tag 7" not in sunday_clock:
                raise RuntimeError(f"expected 'So, Tag 7' in HUD, got {sunday_clock!r}")

            finish(
                f"DOEMITZ_CALENDAR_PIE_OK: 30 citizens, Mo->Di rollover verified, "
                f"Sunday closed shop skipped (Anna target={target}), HUD='{sunday_clock}', default=DoemitzLow",
                True,
            )
            phase = "done"
    except Exception:
        phase = "done"
        finish("DOEMITZ_CALENDAR_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
