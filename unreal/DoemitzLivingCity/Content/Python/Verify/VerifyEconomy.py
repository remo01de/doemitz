from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
cfg_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzSimulationConfig")
APOTHEKE_ID = "poi:osm:node:1794647095"
KAUFHAUS_ID = "place_kaufhaus"
deadline = monotonic() + 90
phase = "test_shop_and_start_shift"
pre_shift_money = 0
expected_wage = 0


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def check(_delta_seconds):
    global phase, pre_shift_money, expected_wage
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
        cfgs = unreal.GameplayStatics.get_all_actors_of_class(world, cfg_class)
        if sub is None or sub.get_citizen_count() == 0 or pawn is None or len(cfgs) != 1:
            return
        widget = cfgs[0].get_clock_widget()
        if widget is None:
            return

        if phase == "test_shop_and_start_shift":
            # 1. Starting balance from Data Asset (125,00 EUR = 12500 ct)
            start_money = sub.get_player_money_cents()
            if start_money != 12500:
                raise RuntimeError(f"expected starting balance 12500 ct, got {start_money}")
            widget.refresh_display()
            money_hud = widget.get_money_text_string()
            if "125,00 EUR" not in money_hud:
                raise RuntimeError(f"unexpected money HUD: {money_hud!r}")

            # 2. Buy Pflasterset (395 ct) at Fritz-Reuter-Apotheke on Monday 10:00
            sub.set_day_number(1)
            sub.set_time_of_day_minutes(600.0)
            if not sub.buy_item(APOTHEKE_ID, "item_pflaster", 1):
                raise RuntimeError("BuyItem(item_pflaster) unexpectedly failed")
            if sub.get_player_money_cents() != 12105:
                raise RuntimeError(f"expected 12105 ct after purchase, got {sub.get_player_money_cents()}")
            if sub.get_inventory_quantity("item_pflaster") != 1:
                raise RuntimeError(f"expected inventory qty 1, got {sub.get_inventory_quantity('item_pflaster')}")
            if sub.get_ledger_count() != 1:
                raise RuntimeError(f"expected 1 ledger entry, got {sub.get_ledger_count()}")
            ap_daily, ap_weekly = sub.get_place_revenue(APOTHEKE_ID)
            if ap_daily != 395 or ap_weekly != 395:
                raise RuntimeError(f"expected Apotheke revenue 395/395, got {ap_daily}/{ap_weekly}")

            # 3. Buy without sufficient funds must fail cleanly
            sub.set_player_money_cents_for_test(100)
            if sub.buy_item(APOTHEKE_ID, "item_pflaster", 1):
                raise RuntimeError("BuyItem should fail with insufficient funds")
            if sub.get_player_money_cents() != 100 or sub.get_inventory_quantity("item_pflaster") != 1:
                raise RuntimeError("failed purchase mutated money or inventory")
            widget.refresh_display()
            notice_text = widget.get_notice_text_string()
            if "Nicht genug Geld f\u00fcr" not in notice_text:
                raise RuntimeError(f"expected insufficient funds UI notice with umlaut, got {notice_text!r}")

            # 4. Accept job at Kaufhaus (09:00-13:00, 1450 ct/h) and start 1 hour late (10:00 -> 3h = 4350 ct)
            if not sub.accept_job(KAUFHAUS_ID):
                raise RuntimeError("AcceptJob at Kaufhaus failed")
            if str(sub.get_active_job_id()) != "job_kaufhaus_verkauf":
                raise RuntimeError(f"unexpected active job: {sub.get_active_job_id()}")

            pre_shift_money = sub.get_player_money_cents()
            expected_wage = 4350  # 3 hours * 1450 ct/h (proportional reduction for 1h lateness)
            if not sub.start_work_shift(KAUFHAUS_ID):
                raise RuntimeError("StartWorkShift at Kaufhaus failed")
            if not sub.is_working_shift():
                raise RuntimeError("expected IsWorkingShift() == True")
            if abs(sub.get_time_scale() - 900.0) > 1.0:
                raise RuntimeError(f"expected 15x (900.0) time scale during shift, got {sub.get_time_scale()}")
            if not pawn.get_editor_property("hidden"):
                raise RuntimeError("expected player pawn to be hidden during work shift")

            # Fast-forward PIE to complete the shift (10:00 -> 13:00 = 180 sim minutes; at 15x = 12s -> 1.5s at 8x dilation)
            unreal.GameplayStatics.set_global_time_dilation(world, 8.0)
            phase = "wait_shift_end"
            return

        if phase == "wait_shift_end":
            if sub.is_working_shift():
                return
            if pawn.get_editor_property("hidden"):
                raise RuntimeError("player pawn remained hidden after shift ended")
            post_money = sub.get_player_money_cents()
            if post_money != pre_shift_money + expected_wage:
                raise RuntimeError(f"expected {pre_shift_money + expected_wage} ct after shift, got {post_money}")

            # Now verify citizen shopping revenue at normal 1x clock (12:30 -> Anna/Dieter arrive at Kaufhaus and shop)
            sub.set_time_of_day_minutes(750.0)
            # Anna walks 127 m (94 s) from the Amtsverwaltung; at 1x (60) that is 94 game minutes, longer than her
            # 60 min shopping slot. Half speed lets her arrive inside the slot (Sprint 14: no other Kaufhaus shopper).
            sub.set_time_scale(30.0)
            unreal.GameplayStatics.set_global_time_dilation(world, 8.0)
            phase = "wait_citizen_revenue"
            return

        if phase == "wait_citizen_revenue":
            kh_daily, kh_weekly = sub.get_place_revenue(KAUFHAUS_ID)
            if kh_daily <= 0:
                return
            if kh_weekly < kh_daily:
                raise RuntimeError(f"weekly revenue {kh_weekly} < daily {kh_daily}")

            finish(
                f"DOEMITZ_ECONOMY_PIE_OK: purchase -395ct & insufficient funds verified, "
                f"late shift paid +{expected_wage}ct (total={sub.get_player_money_cents()}ct), "
                f"Kaufhaus citizen revenue daily={kh_daily}ct weekly={kh_weekly}ct",
                True,
            )
            phase = "done"
    except Exception:
        phase = "done"
        finish("DOEMITZ_ECONOMY_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
