from time import monotonic
import traceback

import unreal

editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
deadline = monotonic() + 120

# Real OSM parking lot (way 1345175489, access_edge = edge:osm:way:157877528:0:0:fwd)
TARGET_LOT = "parking:osm:way:1345175489"
ACCESS_EDGE = "edge:osm:way:157877528:0:0:fwd"
VID = "altstadt_vehicle_01"

phase = "setup"
saw_parking = False
saw_parked = False
saw_leaving = False
parked_occupancy = 0


def finish(message, success):
    unreal.unregister_slate_post_tick_callback(handle)
    (unreal.log if success else unreal.log_error)(message)
    level.editor_request_end_play()
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def get_vstate(sub, vid):
    res = sub.get_vehicle_state(vid)
    return res[1] if isinstance(res, tuple) else res


def get_lot(sub, lot_id):
    res = sub.get_parking_lot_state(lot_id)
    return res[1] if isinstance(res, tuple) else res


def check(_delta_seconds):
    global phase, saw_parking, saw_parked, saw_leaving, parked_occupancy
    try:
        if monotonic() > deadline:
            raise RuntimeError(f"timed out during {phase} (parking={saw_parking}, parked={saw_parked}, leaving={saw_leaving})")
        if not level.is_in_play_in_editor():
            return
        world = editor.get_game_world()
        if world is None:
            return
        sub = unreal.DoemitzTrafficSubsystem.get(world)
        if sub is None or sub.get_vehicle_count() < 8:
            return

        if phase == "setup":
            if sub.get_parking_lot_count() < 9:
                raise RuntimeError(f"expected >=9 parking lots, got {sub.get_parking_lot_count()}")
            lot = get_lot(sub, TARGET_LOT)
            if lot is None or lot.get_editor_property("capacity") < 1:
                raise RuntimeError(f"target parking lot {TARGET_LOT} invalid")

            # Position vehicle_01 right on the access edge heading into TARGET_LOT
            if not sub.set_vehicle_edge_position_for_test(VID, ACCESS_EDGE, 50.0, 300.0):
                raise RuntimeError(f"failed to position {VID} on {ACCESS_EDGE}")
            if not sub.set_vehicle_target_parking_for_test(VID, TARGET_LOT):
                raise RuntimeError(f"failed to set target parking lot {TARGET_LOT}")
            unreal.GameplayStatics.set_global_time_dilation(world, 6.0)
            phase = "observe_cycle"
            return

        if phase == "observe_cycle":
            vst = get_vstate(sub, VID)
            vphase = vst.get_editor_property("phase")

            if vphase == unreal.DoemitzVehiclePhase.PARKING:
                saw_parking = True
            elif vphase == unreal.DoemitzVehiclePhase.PARKED:
                saw_parked = True
                lot = get_lot(sub, TARGET_LOT)
                occ = int(lot.get_editor_property("occupied_count"))
                if occ < 1:
                    raise RuntimeError(f"vehicle parked in {TARGET_LOT} but occupied_count={occ}")
                parked_occupancy = max(parked_occupancy, occ)
            elif vphase == unreal.DoemitzVehiclePhase.LEAVING:
                saw_leaving = True
            elif vphase == unreal.DoemitzVehiclePhase.DRIVING and saw_parked:
                # Completed full cycle: Driving -> Parking -> Parked -> Leaving -> Driving!
                new_target = str(vst.get_editor_property("target_parking_lot_id"))
                if not new_target or new_target == TARGET_LOT:
                    raise RuntimeError(f"vehicle did not pick a new destination parking lot after leaving: {new_target!r}")
                finish(
                    f"DOEMITZ_PARKING_PIE_OK: {sub.get_parking_lot_count()} lots loaded, {VID} completed "
                    f"Driving->Parking->Parked (lot={TARGET_LOT}, occ={parked_occupancy})->Leaving->Driving "
                    f"(next_target={new_target})",
                    True,
                )
                phase = "done"
    except Exception:
        phase = "done"
        finish("DOEMITZ_PARKING_PIE_FAILED: " + traceback.format_exc(), False)


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle = unreal.register_slate_post_tick_callback(check)
level.editor_request_begin_play()
