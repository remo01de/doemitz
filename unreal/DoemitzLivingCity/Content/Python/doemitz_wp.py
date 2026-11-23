"""World Partition helpers for editor scripts (Sprint 14).

Since Sprint 14 the generated city meshes, terrain tiles and prop actors are spatially loaded. The game streams
them around the player; the editor only shows what is loaded in the editor, so editor scripts that render the
map (screenshots) load every actor first.
"""

import unreal


def load_all_actors():
    """Load all World Partition actors of the open editor map; returns the number of actors requested."""
    lib = unreal.WorldPartitionBlueprintLibrary
    res = lib.get_actor_descs()
    descs = res[1] if isinstance(res, tuple) else res
    guids = []
    for desc in descs or []:
        try:
            if desc.get_editor_property("is_spatially_loaded"):
                guids.append(desc.get_editor_property("guid"))
        except Exception:
            guids.append(desc.get_editor_property("guid"))
    if guids:
        lib.load_actors(guids)
    unreal.log(f"DOEMITZ_WP_LOAD_ALL: {len(guids)} spatially loaded actors loaded in the editor")
    return len(guids)
