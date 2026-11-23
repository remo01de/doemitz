from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
cfg_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzSimulationConfig")
deadline = monotonic() + 90
phase = "wait_anna_commute"
dialog_cid = "citizen_anna_01"
dialog_saved_loc = None
dialog_ticks = 0


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def get_state(sub, cid):
    res = sub.get_citizen_state(cid)
    return res[1] if isinstance(res, tuple) else res


def check(_delta_seconds):
    global phase, dialog_saved_loc, dialog_ticks
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during {phase}")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzSimulationSubsystem.get(world)
        cit = unreal.DoemitzCitizenSubsystem.get(world)
        econ = unreal.DoemitzEconomySubsystem.get(world)
        tsk = unreal.DoemitzTaskSubsystem.get(world)
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        cfgs = unreal.GameplayStatics.get_all_actors_of_class(world, cfg_class)
        if sub is None or cit is None or econ is None or tsk is None or cit.get_citizen_count() < 30 or pawn is None or len(cfgs) != 1:
            return
        cfg = cfgs[0]
        clock_widget = cfg.get_clock_widget()
        interaction = pawn.get_interaction_component()
        if clock_widget is None or interaction is None:
            return

        if phase == "wait_anna_commute":
            # Start Anna commuting along Goethestrasse (07:55 = 475 min) so she is moving mid-sidewalk away from doors
            sub.set_day_number(1)
            sub.set_time_of_day_minutes(475.0)
            sub.set_time_scale(sub.get_base_time_scale())
            unreal.GameplayStatics.set_global_time_dilation(world, 4.0)
            phase = "open_dialog"
            return

        if phase == "open_dialog":
            cstate = get_state(cit, dialog_cid)
            if not cstate.get_editor_property("is_moving") or cstate.get_editor_property("route_progress_cm") < 400.0:
                return
            unreal.GameplayStatics.set_global_time_dilation(world, 1.0)
            dialog_saved_loc = cstate.get_editor_property("world_location")
            pawn.set_actor_location(dialog_saved_loc + unreal.Vector(40.0, 0.0, 90.0), False, True)
            interaction.refresh_nearest_entrance()
            if not interaction.has_interactable_citizen() or str(interaction.get_nearest_citizen_id()) != dialog_cid:
                raise RuntimeError(
                    f"expected nearest citizen {dialog_cid}, got place={interaction.get_nearest_place_id()} cit={interaction.get_nearest_citizen_id()}"
                )
            if not interaction.try_interact() or not interaction.is_citizen_dialog_open():
                raise RuntimeError("TryInteract did not open CitizenDialogWidget")
            if not cit.is_citizen_dialog_paused(dialog_cid):
                raise RuntimeError("citizen was not paused during dialog")
            dlg = interaction.get_active_citizen_dialog_widget()
            if dlg is None or "Anna" not in dlg.get_header_text_string() or "Unterwegs" not in dlg.get_activity_text_string():
                raise RuntimeError(f"unexpected dialog texts: hdr={dlg.get_header_text_string() if dlg else None!r} act={dlg.get_activity_text_string() if dlg else None!r}")

            dialog_ticks = 0
            phase = "verify_citizen_paused"
            return

        if phase == "verify_citizen_paused":
            dialog_ticks += 1
            if dialog_ticks < 10:
                return
            cstate_now = get_state(cit, dialog_cid)
            if (cstate_now.get_editor_property("world_location") - dialog_saved_loc).length() > 1.0:
                raise RuntimeError("moving citizen moved while paused in dialog!")
            interaction.close_menu()
            if cit.is_citizen_dialog_paused(dialog_cid):
                raise RuntimeError("citizen remained paused after closing dialog")
            unreal.GameplayStatics.set_global_time_dilation(world, 4.0)
            dialog_ticks = 0
            phase = "verify_citizen_resumed"
            return

        if phase == "verify_citizen_resumed":
            dialog_ticks += 1
            cstate_now = get_state(cit, dialog_cid)
            moved_after = (cstate_now.get_editor_property("world_location") - dialog_saved_loc).length()
            if moved_after < 25.0:
                if dialog_ticks > 60:
                    raise RuntimeError(f"citizen did not resume moving after dialog closed (moved={moved_after:.1f} cm)")
                return

            # Switch to Monday 10:30 so all shops, pharmacies, and offices are open for Errand & Fetch verification
            unreal.GameplayStatics.set_global_time_dilation(world, 1.0)
            sub.set_day_number(1)
            sub.set_time_of_day_minutes(630.0)
            sub.set_time_scale(sub.get_base_time_scale())

            avail = tsk.get_tasks_by_status(unreal.DoemitzTaskStatus.AVAILABLE)
            if not (3 <= len(avail) <= 5):
                raise RuntimeError(f"expected 3-5 daily tasks, got {len(avail)}")

            errand = next((t for t in avail if t.get_editor_property("task_type") == unreal.DoemitzTaskType.ERRAND), None)
            fetch = next((t for t in avail if t.get_editor_property("task_type") == unreal.DoemitzTaskType.FETCH), None)
            if errand is None or fetch is None:
                raise RuntimeError("expected at least one Errand and one Fetch task on Monday")
            extra = next((t for t in avail if str(t.get_editor_property("task_id")) not in {
                str(errand.get_editor_property("task_id")),
                str(fetch.get_editor_property("task_id")),
            }), None)
            if extra is None:
                raise RuntimeError("expected a 3rd available task for missed-deadline test")

            # 2. Complete Errand (Botengang): accept -> HUD shows task -> pickup -> deliver -> ledger + reward
            errand_id = str(errand.get_editor_property("task_id"))
            errand_reward = int(errand.get_editor_property("reward_cents"))
            money_before = econ.get_player_money_cents()
            ledger_before = econ.get_ledger_count()

            if not tsk.accept_task(errand_id):
                raise RuntimeError(f"AcceptTask({errand_id}) failed")
            clock_widget.refresh_display()
            hud_task = clock_widget.get_active_task_text_string()
            if "Aufgabe:" not in hud_task or "Abholen" not in hud_task:
                raise RuntimeError(f"unexpected active task HUD before pickup: {hud_task!r}")

            if not tsk.pickup_task_parcel(errand_id):
                raise RuntimeError(f"PickupTaskParcel({errand_id}) failed")
            clock_widget.refresh_display()
            hud_task_del = clock_widget.get_active_task_text_string()
            if "Abgeben" not in hud_task_del:
                raise RuntimeError(f"unexpected active task HUD after pickup: {hud_task_del!r}")

            if not tsk.deliver_task_parcel(errand_id):
                raise RuntimeError(f"DeliverTaskParcel({errand_id}) failed")
            if econ.get_player_money_cents() != money_before + errand_reward:
                raise RuntimeError("errand reward not credited to player balance")
            if econ.get_ledger_count() != ledger_before + 1:
                raise RuntimeError("errand reward not recorded in ledger")

            # 3. Complete Fetch (Besorgung): accept -> buy item -> hand over -> item consumed + reward
            fetch_id = str(fetch.get_editor_property("task_id"))
            fetch_item = str(fetch.get_editor_property("requested_item_id"))
            fetch_shop = str(fetch.get_editor_property("preferred_shop_place_id"))
            fetch_reward = int(fetch.get_editor_property("reward_cents"))

            if not tsk.accept_task(fetch_id):
                raise RuntimeError(f"AcceptTask({fetch_id}) failed")
            if tsk.complete_fetch_task(fetch_id):
                raise RuntimeError("CompleteFetchTask should fail without requested item in inventory")
            if not econ.buy_item(fetch_shop, fetch_item, 1):
                raise RuntimeError(f"BuyItem({fetch_shop}, {fetch_item}) failed")
            money_after_buy = econ.get_player_money_cents()
            if not tsk.complete_fetch_task(fetch_id):
                raise RuntimeError(f"CompleteFetchTask({fetch_id}) failed after purchase")
            if econ.get_inventory_quantity(fetch_item) != 0:
                raise RuntimeError("fetch item was not consumed from inventory")
            if econ.get_player_money_cents() != money_after_buy + fetch_reward:
                raise RuntimeError("fetch reward was not credited")

            # 4. Missed deadline: accept 3rd task -> advance past deadline -> status MISSED, no reward
            extra_id = str(extra.get_editor_property("task_id"))
            extra_deadline = int(extra.get_editor_property("deadline_minute"))
            money_before_miss = econ.get_player_money_cents()
            if not tsk.accept_task(extra_id):
                raise RuntimeError(f"AcceptTask({extra_id}) failed")
            sub.set_time_of_day_minutes(float(min(1439, extra_deadline + 5)))
            missed_list = tsk.get_tasks_by_status(unreal.DoemitzTaskStatus.MISSED)
            if not any(str(t.get_editor_property("task_id")) == extra_id for t in missed_list):
                raise RuntimeError("task did not transition to MISSED after passing deadline")
            if econ.get_player_money_cents() != money_before_miss:
                raise RuntimeError("missed task unexpectedly paid a reward")

            # 5. Open Task Journal (J) and verify summary counts
            cfg.set_task_journal_open(True)
            if not cfg.is_task_journal_open():
                raise RuntimeError("SetTaskJournalOpen(True) failed")
            journal = cfg.get_task_journal_widget()
            journal.refresh_contents()
            summary = journal.get_summary_text_string()
            if "Erledigt: 2" not in summary or "Verpasst: 1" not in summary:
                raise RuntimeError(f"unexpected Task Journal summary: {summary!r}")
            cfg.set_task_journal_open(False)

            finish(
                f"DOEMITZ_TASKS_PIE_OK: dialog pause & resume verified ({dialog_cid}, resumed {moved_after:.1f} cm), "
                f"errand={errand_id} (+{errand_reward}ct), fetch={fetch_id} (+{fetch_reward}ct), "
                f"missed={extra_id} (no reward), journal='{summary}'",
                True,
            )
            phase = "done"
    except Exception:
        phase = "done"
        finish("DOEMITZ_TASKS_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
