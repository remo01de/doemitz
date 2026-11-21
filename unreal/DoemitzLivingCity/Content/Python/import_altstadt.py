"""Create or update the generated Altstadt level from the offline mesh package."""

import json
from math import atan2, degrees
from pathlib import Path

import unreal
from doemitz_citizen_mesh import stylized_citizen
from doemitz_prop_meshes import (
    street_bench,
    street_bollard,
    street_lamp_glow,
    street_lamp_metal,
    street_planter,
    stylized_bush,
    stylized_tree,
)
from doemitz_vehicle_mesh import compact_car


PROJECT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
PACKAGE = PROJECT.parents[1] / "data/processed/doemitz-altstadt/unreal-city-meshes.json"
MAP = "/Game/Maps/DoemitzAltstadt"
ASSETS = "/Game/Generated/DoemitzAltstadt"
GENERATOR_TAG = "DoemitzAltstadtImport"
EDITOR = unreal.EditorAssetLibrary
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
TOOLS = unreal.AssetToolsHelpers.get_asset_tools()


def ue_position(point):
    east, north, height = point
    return unreal.Vector(north * 100, east * 100, height * 100)


def _build_patterned_color(asset, color, tile_u, tile_v, darken_factor, contrast):
    """Build a lightweight procedural tile/brick/cobble/plaster pattern using standard UE material nodes."""
    mel = unreal.MaterialEditingLibrary
    dark_color = tuple(max(0.0, c * darken_factor) for c in color)

    col_a = mel.create_material_expression(asset, unreal.MaterialExpressionConstant3Vector, -600, -140)
    col_a.set_editor_property("constant", unreal.LinearColor(*color, 1))
    col_b = mel.create_material_expression(asset, unreal.MaterialExpressionConstant3Vector, -600, 20)
    col_b.set_editor_property("constant", unreal.LinearColor(*dark_color, 1))

    uv = mel.create_material_expression(asset, unreal.MaterialExpressionTextureCoordinate, -1000, 180)
    uv.set_editor_property("u_tiling", float(tile_u))
    uv.set_editor_property("v_tiling", float(tile_v))

    mask_u = mel.create_material_expression(asset, unreal.MaterialExpressionComponentMask, -820, 120)
    mask_u.set_editor_property("r", True)
    mask_u.set_editor_property("g", False)
    mask_u.set_editor_property("b", False)
    mask_u.set_editor_property("a", False)
    mel.connect_material_expressions(uv, "", mask_u, "")

    mask_v = mel.create_material_expression(asset, unreal.MaterialExpressionComponentMask, -820, 240)
    mask_v.set_editor_property("r", False)
    mask_v.set_editor_property("g", True)
    mask_v.set_editor_property("b", False)
    mask_v.set_editor_property("a", False)
    mel.connect_material_expressions(uv, "", mask_v, "")

    sin_u = mel.create_material_expression(asset, unreal.MaterialExpressionSine, -660, 120)
    mel.connect_material_expressions(mask_u, "", sin_u, "")
    sin_v = mel.create_material_expression(asset, unreal.MaterialExpressionSine, -660, 240)
    mel.connect_material_expressions(mask_v, "", sin_v, "")

    mul_uv = mel.create_material_expression(asset, unreal.MaterialExpressionMultiply, -500, 180)
    mel.connect_material_expressions(sin_u, "", mul_uv, "A")
    mel.connect_material_expressions(sin_v, "", mul_uv, "B")

    # Map [-1, 1] -> [0, 1] scaled by contrast
    scale = mel.create_material_expression(asset, unreal.MaterialExpressionConstant, -500, 300)
    scale.set_editor_property("r", 0.5 * contrast)
    bias = mel.create_material_expression(asset, unreal.MaterialExpressionConstant, -360, 300)
    bias.set_editor_property("r", 0.5)

    mul_c = mel.create_material_expression(asset, unreal.MaterialExpressionMultiply, -360, 180)
    mel.connect_material_expressions(mul_uv, "", mul_c, "A")
    mel.connect_material_expressions(scale, "", mul_c, "B")

    add_b = mel.create_material_expression(asset, unreal.MaterialExpressionAdd, -220, 180)
    mel.connect_material_expressions(mul_c, "", add_b, "A")
    mel.connect_material_expressions(bias, "", add_b, "B")

    lerp = mel.create_material_expression(asset, unreal.MaterialExpressionLinearInterpolate, -80, 0)
    mel.connect_material_expressions(col_b, "", lerp, "A")
    mel.connect_material_expressions(col_a, "", lerp, "B")
    mel.connect_material_expressions(add_b, "", lerp, "Alpha")
    return lerp


PROCEDURAL_PATTERNS = {
    "Paving": (14.0, 14.0, 0.66, 0.95),
    "Sidewalks": (6.0, 6.0, 0.78, 0.80),
    "Roads": (4.0, 4.0, 0.86, 0.45),
    "Paths": (9.0, 9.0, 0.78, 0.70),
    "RoofsTerracotta": (10.0, 22.0, 0.62, 0.95),
    "RoofsClay": (10.0, 22.0, 0.64, 0.95),
    "RoofsSlate": (10.0, 20.0, 0.68, 0.85),
    "StoneTrim": (6.0, 12.0, 0.72, 0.85),
    "Terrain": (0.8, 0.8, 0.82, 0.55),
    "WallsCream": (1.5, 1.5, 0.90, 0.45),
    "WallsOchre": (1.5, 1.5, 0.88, 0.50),
    "WallsTerracotta": (1.5, 1.5, 0.86, 0.55),
    "WallsSage": (1.5, 1.5, 0.88, 0.50),
    "WallsSand": (1.5, 1.5, 0.88, 0.45),
    "WallsBrick": (8.0, 16.0, 0.68, 0.90),
}


def material(name, color):
    path = f"{ASSETS}/M_{name}"
    asset = EDITOR.load_asset(path) if EDITOR.does_asset_exist(path) else None
    if asset is None:
        asset = TOOLS.create_asset(f"M_{name}", ASSETS, unreal.Material, unreal.MaterialFactoryNew())
    else:
        unreal.MaterialEditingLibrary.delete_all_material_expressions(asset)

    if color is None:
        base = unreal.MaterialEditingLibrary.create_material_expression(
            asset, unreal.MaterialExpressionVertexColor, -300, 0
        )
    elif name in PROCEDURAL_PATTERNS:
        tile_u, tile_v, darken, contrast = PROCEDURAL_PATTERNS[name]
        base = _build_patterned_color(asset, color, tile_u, tile_v, darken, contrast)
    else:
        base = unreal.MaterialEditingLibrary.create_material_expression(
            asset, unreal.MaterialExpressionConstant3Vector, -300, 0
        )
        base.set_editor_property("constant", unreal.LinearColor(*color, 1))
    unreal.MaterialEditingLibrary.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)

    roughness_val = 0.85
    metallic_val = 0.0
    emissive_color = None
    if name == "Water":
        roughness_val = 0.12
    elif name == "WindowGlass":
        roughness_val = 0.14
        metallic_val = 0.25
    elif name in {"LampMetal", "PropLampMetal", "PropBollard"}:
        roughness_val = 0.42
        metallic_val = 0.75
    elif name in {"LanternGlow", "PropLanternGlow"}:
        roughness_val = 0.25
        emissive_color = (3.8, 2.6, 1.0)

    roughness = unreal.MaterialEditingLibrary.create_material_expression(
        asset, unreal.MaterialExpressionConstant, -300, 150
    )
    roughness.set_editor_property("r", roughness_val)
    unreal.MaterialEditingLibrary.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)

    if metallic_val > 0.0:
        metallic = unreal.MaterialEditingLibrary.create_material_expression(
            asset, unreal.MaterialExpressionConstant, -300, 260
        )
        metallic.set_editor_property("r", metallic_val)
        unreal.MaterialEditingLibrary.connect_material_property(metallic, "", unreal.MaterialProperty.MP_METALLIC)

    if emissive_color is not None:
        emissive = unreal.MaterialEditingLibrary.create_material_expression(
            asset, unreal.MaterialExpressionConstant3Vector, -300, 360
        )
        emissive.set_editor_property("constant", unreal.LinearColor(*emissive_color, 1))
        unreal.MaterialEditingLibrary.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    unreal.MaterialEditingLibrary.recompile_material(asset)
    if not EDITOR.save_loaded_asset(asset):
        raise RuntimeError(f"Could not save material {path}")
    return asset


def static_mesh(name, source):
    path = f"{ASSETS}/SM_{name}"
    mesh = unreal.DynamicMesh()
    buffers = unreal.GeometryScriptSimpleMeshBuffers()
    buffers.set_editor_property("vertices", [ue_position(point) for point in source["vertices"]])
    buffers.set_editor_property("triangles", [unreal.IntVector(*indices) for indices in source["triangles"]])
    buffers.set_editor_property("uv0", [
        unreal.Vector2D(east / 4, (north + height) / 4) for east, north, height in source["vertices"]
    ])
    if "vertex_colors" in source:
        buffers.set_editor_property("vertex_colors", [
            unreal.LinearColor(*color, 1) for color in source["vertex_colors"]
        ])
    unreal.GeometryScript_MeshEdits.append_buffers_to_mesh(mesh, buffers)
    if mesh.get_triangle_count() != len(source["triangles"]):
        raise RuntimeError(
            f"Triangle count changed during import of {name}: "
            f"{len(source['triangles'])} to {mesh.get_triangle_count()}"
        )

    if EDITOR.does_asset_exist(path):
        asset = EDITOR.load_asset(path)
        options = unreal.GeometryScriptCopyMeshToAssetOptions(enable_recompute_normals=True)
        target = unreal.GeometryScriptMeshWriteLOD()
        _, outcome = unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(mesh, asset, options, target)
    else:
        options = unreal.GeometryScriptCreateNewStaticMeshAssetOptions(
            enable_recompute_normals=True,
            enable_collision=source["collision"],
            collision_mode=unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE,
        )
        asset, outcome = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(
            mesh, path, options
        )
    if asset is None or outcome != unreal.GeometryScriptOutcomePins.SUCCESS:
        raise RuntimeError(f"Could not build static mesh {path}: {outcome}")
    asset.set_material(0, material(name, source.get("color")))
    if not EDITOR.save_loaded_asset(asset):
        raise RuntimeError(f"Could not save mesh {path}")
    return asset


def place(existing, name, actor_class, position, rotation=None):
    rotation = rotation or unreal.Rotator()
    actor = existing.get(name)
    if actor is None:
        actor = ACTORS.spawn_actor_from_class(actor_class, position, rotation)
        if actor is None:
            raise RuntimeError(f"Could not spawn {name}")
        actor.set_actor_label(name)
        actor.set_editor_property("tags", [GENERATOR_TAG])
    elif actor.get_class() != (actor_class if isinstance(actor_class, unreal.Class) else actor_class.static_class()):
        raise RuntimeError(f"{name} has unexpected class {actor.get_class().get_name()}")
    else:
        actor.set_actor_location(position, False, False)
        actor.set_actor_rotation(rotation, False)
    actor.set_editor_property("is_spatially_loaded", False)
    return actor


def place_instanced_props(existing, prop_instances):
    hism_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzInstancedPropActor")
    if not hism_class:
        raise RuntimeError("Build the DoemitzLivingCityEditor target before importing HISM props")

    def make_transforms(entries, has_scale=False):
        result = []
        for entry in entries:
            pos = ue_position(entry[:3])
            rot = unreal.Rotator(0.0, float(entry[3]), 0.0)
            s = float(entry[4]) if has_scale else 1.0
            result.append(unreal.Transform(pos, rot, unreal.Vector(s, s, s)))
        return result

    groups = [
        ("Altstadt HISM Lamps Metal", "PropLampMetal", street_lamp_metal(), make_transforms(prop_instances.get("street_lamps", []))),
        ("Altstadt HISM Lamps Glow", "PropLanternGlow", street_lamp_glow(), make_transforms(prop_instances.get("street_lamps", []))),
        ("Altstadt HISM Benches", "PropBench", street_bench(), make_transforms(prop_instances.get("benches", []))),
        ("Altstadt HISM Planters", "PropPlanter", street_planter(), make_transforms(prop_instances.get("planters", []))),
        ("Altstadt HISM Bollards", "PropBollard", street_bollard(), make_transforms(prop_instances.get("bollards", []))),
    ]

    for variant in range(3):
        tree_entries = [e for e in prop_instances.get("trees", []) if int(e[5]) == variant]
        groups.append((f"Altstadt HISM Trees {variant}", f"PropTree_{variant}", stylized_tree(variant), make_transforms(tree_entries, has_scale=True)))
        bush_entries = [e for e in prop_instances.get("bushes", []) if int(e[5]) == variant]
        groups.append((f"Altstadt HISM Bushes {variant}", f"PropBush_{variant}", stylized_bush(variant), make_transforms(bush_entries, has_scale=True)))

    active_labels = set()
    total_instances = 0
    for label, mesh_name, mesh_data, transforms in groups:
        if not transforms:
            continue
        active_labels.add(label)
        actor = place(existing, label, hism_class, unreal.Vector())
        hism_comp = actor.get_editor_property("hism_component")
        hism_comp.set_static_mesh(static_mesh(mesh_name, mesh_data))
        actor.set_instances(transforms)
        total_instances += len(transforms)

    for label, actor in list(existing.items()):
        if label.startswith("Altstadt HISM ") and label not in active_labels:
            if not ACTORS.destroy_actor(actor):
                raise RuntimeError(f"Could not remove obsolete HISM prop actor {label}")
    unreal.log(f"DOEMITZ_HISM_IMPORT_OK: {len(active_labels)} HISM actors, {total_instances} instances")


def place_traffic_network(existing, road_graph, traffic_network, legacy_vehicle):
    vehicle_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzTrafficVehicle")
    if not vehicle_class:
        raise RuntimeError("Build the DoemitzLivingCityEditor target before importing traffic vehicles")

    if not traffic_network or not road_graph:
        place_vehicle(existing, legacy_vehicle)
        return [], [], 202607

    # Remove legacy single test vehicle if present
    legacy_actor = existing.get("Altstadt Test Vehicle")
    if legacy_actor and not ACTORS.destroy_actor(legacy_actor):
        raise RuntimeError("Could not remove obsolete Altstadt Test Vehicle")

    edges_by_id = {edge["id"]: edge for edge in road_graph["edges"]}
    edge_structs = []
    for edge in road_graph["edges"]:
        edef = unreal.DoemitzRoadEdgeDefinition()
        edef.set_editor_property("edge_id", edge["id"])
        edef.set_editor_property("from_node_id", edge["from_node"])
        edef.set_editor_property("to_node_id", edge["to_node"])
        edef.set_editor_property("one_way", bool(edge["oneway"]))
        edef.set_editor_property("dead_end", bool(edge["dead_end"]))
        edef.set_editor_property("width_cm", float(edge["width_m"]) * 100.0)
        edef.set_editor_property("speed_limit_cm_per_second", float(edge["speed_kmh"]) / 0.036)
        edef.set_editor_property("points", list(map(ue_position, edge["points_m"])))
        edge_structs.append(edef)

    vehicle_structs = []
    active_labels = set()
    for entry in traffic_network["vehicles"]:
        vid = entry["id"]
        vdef = unreal.DoemitzVehicleDefinition()
        vdef.set_editor_property("vehicle_id", vid)
        vdef.set_editor_property("start_edge_id", entry["start_edge_id"])
        vdef.set_editor_property("start_distance_cm", float(entry["start_distance_m"]) * 100.0)
        vehicle_structs.append(vdef)

        edge = edges_by_id[entry["start_edge_id"]]
        p0 = ue_position(edge["points_m"][0])
        p1 = ue_position(edge["points_m"][1])
        heading = p1 - p0
        yaw = degrees(atan2(heading.y, heading.x))
        label = f"Altstadt Vehicle - {vid}"
        active_labels.add(label)
        actor = place(existing, label, vehicle_class, p0, unreal.Rotator(yaw=yaw))
        actor.get_editor_property("vehicle_mesh").set_static_mesh(
            static_mesh(f"CompactCar_{vid}", compact_car(entry.get("body_color")))
        )
        actor.set_editor_property("vehicle_id", vid)
        actor.set_editor_property("route_id", "")
        actor.set_editor_property("route_points", [])

    for actor in list(ACTORS.get_all_level_actors()):
        if actor.get_class() == vehicle_class and actor.get_actor_label() not in active_labels:
            unreal.log(f"Destroying obsolete vehicle actor: {actor.get_actor_label()}")
            if not ACTORS.destroy_actor(actor):
                raise RuntimeError(f"Could not remove obsolete vehicle actor {actor.get_actor_label()}")
    remaining_vehicles = [
        (a.get_actor_label(), str(a.get_editor_property("vehicle_id")))
        for a in ACTORS.get_all_level_actors() if a.get_class() == vehicle_class
    ]
    unreal.log(f"Remaining vehicle actors in level: {remaining_vehicles}")

    unreal.log(
        f"DOEMITZ_TRAFFIC_NETWORK_IMPORT_OK: {len(vehicle_structs)} vehicles, "
        f"{len(edge_structs)} road edges (seed={traffic_network['seed']})"
    )
    return edge_structs, vehicle_structs, int(traffic_network["seed"])


def place_vehicle(existing, config):
    name = "Altstadt Test Vehicle"
    if not config:
        actor = existing.get(name)
        if actor and not ACTORS.destroy_actor(actor):
            raise RuntimeError(f"Could not remove obsolete generated actor {name}")
        return
    vehicle_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzTrafficVehicle")
    if not vehicle_class:
        raise RuntimeError("Build the DoemitzLivingCityEditor target before importing the vehicle")
    position, ahead = map(ue_position, config["preview_pose_m"])
    heading = ahead - position
    yaw = degrees(atan2(heading.y, heading.x))
    actor = place(existing, name, vehicle_class, position, unreal.Rotator(yaw=yaw))
    actor.get_editor_property("vehicle_mesh").set_static_mesh(static_mesh("CompactCar", compact_car()))
    actor.set_editor_property("vehicle_id", config["id"])
    actor.set_editor_property("route_id", config["route_id"])
    actor.set_editor_property("route_points", list(map(ue_position, config["points_m"])))
    actor.set_editor_property("start_distance_cm", config["start_distance_m"] * 100)
    actor.set_editor_property("speed_cm_per_second", config["speed_kmh"] / 0.036)
    unreal.log(f"DOEMITZ_TRAFFIC_IMPORT_OK: {config['id']}, {config['route_id']}, {config['length_m']:.1f} m")


def place_citizens(existing, config, road_edge_structs=None, vehicle_structs=None, traffic_seed=202607):
    config_name = "Altstadt Simulation Config"
    if not config:
        for label, actor in list(existing.items()):
            if label == config_name or label.startswith("Altstadt Citizen - "):
                if not ACTORS.destroy_actor(actor):
                    raise RuntimeError(f"Could not remove obsolete generated actor {label}")
        return

    config_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzSimulationConfig")
    citizen_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzCitizenActor")
    if not config_class or not citizen_class:
        raise RuntimeError("Build the DoemitzLivingCityEditor target before importing citizens")

    activity_enum = {
        "Home": unreal.DoemitzCitizenActivity.HOME,
        "Commuting": unreal.DoemitzCitizenActivity.COMMUTING,
        "Working": unreal.DoemitzCitizenActivity.WORKING,
        "Shopping": unreal.DoemitzCitizenActivity.SHOPPING,
        "Strolling": unreal.DoemitzCitizenActivity.STROLLING,
    }

    places_by_id = {}
    place_structs = []
    for entry in config["places"]:
        pos = ue_position(entry["access_m"])
        places_by_id[entry["id"]] = pos
        place_struct = unreal.DoemitzPlaceDefinition()
        place_struct.set_editor_property("place_id", entry["id"])
        place_struct.set_editor_property("display_name", entry["name"])
        place_struct.set_editor_property("building_id", entry["building_id"])
        place_struct.set_editor_property("kind", entry["kind"])
        place_struct.set_editor_property("access_location", pos)
        place_structs.append(place_struct)

    route_structs = []
    for entry in config["routes"]:
        route_struct = unreal.DoemitzCitizenRoute()
        route_struct.set_editor_property("from_place_id", entry["from_place_id"])
        route_struct.set_editor_property("to_place_id", entry["to_place_id"])
        route_struct.set_editor_property("points", list(map(ue_position, entry["points_m"])))
        route_structs.append(route_struct)

    citizen_structs = []
    active_labels = set()
    for entry in config["citizens"]:
        schedule_structs = []
        for step in entry["schedule"]:
            sched = unreal.DoemitzScheduleEntry()
            sched.set_editor_property("start_minute", step["start_minute"])
            sched.set_editor_property("activity", activity_enum[step["activity"]])
            sched.set_editor_property("place_id", step["place_id"])
            schedule_structs.append(sched)

        cdef = unreal.DoemitzCitizenDefinition()
        cdef.set_editor_property("citizen_id", entry["id"])
        cdef.set_editor_property("display_name", entry["name"])
        cdef.set_editor_property("home_place_id", entry["home_place_id"])
        cdef.set_editor_property("work_place_id", entry["work_place_id"])
        cdef.set_editor_property("walk_speed_cm_per_second", entry["walk_speed_mps"] * 100.0)
        cdef.set_editor_property("schedule", schedule_structs)
        citizen_structs.append(cdef)

        label = f"Altstadt Citizen - {entry['id']}"
        active_labels.add(label)
        spawn_pos = places_by_id[entry["home_place_id"]]
        actor = place(existing, label, citizen_class, spawn_pos)
        mesh_name = f"Citizen_{entry['id']}"
        actor.get_editor_property("citizen_mesh").set_static_mesh(
            static_mesh(mesh_name, stylized_citizen(entry["coat_color"]))
        )
        actor.set_editor_property("citizen_id", entry["id"])

    for label, actor in list(existing.items()):
        if label.startswith("Altstadt Citizen - ") and label not in active_labels:
            if not ACTORS.destroy_actor(actor):
                raise RuntimeError(f"Could not remove obsolete citizen actor {label}")

    sim_actor = place(existing, config_name, config_class, unreal.Vector())
    sim_actor.set_editor_property("start_minute", config["clock"]["start_minute"])
    sim_actor.set_editor_property("time_scale", config["clock"]["time_scale"])
    sim_actor.set_editor_property("places", place_structs)
    sim_actor.set_editor_property("routes", route_structs)
    sim_actor.set_editor_property("citizens", citizen_structs)
    if road_edge_structs is not None and vehicle_structs is not None:
        sim_actor.set_editor_property("traffic_seed", traffic_seed)
        sim_actor.set_editor_property("road_edges", road_edge_structs)
        sim_actor.set_editor_property("vehicles", vehicle_structs)
    unreal.log(
        f"DOEMITZ_CITIZENS_IMPORT_OK: {len(citizen_structs)} citizens, "
        f"{len(place_structs)} places, {len(route_structs)} routes"
    )


def import_level(package):
    if package["schema_version"] != 1:
        raise ValueError("Unsupported mesh package version")
    assets = {name: static_mesh(name, source) for name, source in package["meshes"].items()}
    if EDITOR.does_asset_exist(MAP):
        loaded = LEVELS.load_level(MAP)
    else:
        loaded = LEVELS.new_level(MAP, is_partitioned_world=True)
    if not loaded:
        raise RuntimeError(f"Could not open {MAP}")
    existing = {}
    for actor in ACTORS.get_all_level_actors():
        if actor.actor_has_tag(GENERATOR_TAG):
            name = actor.get_actor_label()
            if name in existing:
                raise RuntimeError(f"Duplicate generated actor {name}")
            existing[name] = actor

    mesh_actors = {}
    for name, asset in assets.items():
        actor = place(existing, f"Altstadt {name}", unreal.StaticMeshActor, unreal.Vector())
        mesh_actors[name] = actor
        component = actor.static_mesh_component
        component.set_static_mesh(asset)
        profile = "BlockAll" if package["meshes"][name]["collision"] else "NoCollision"
        component.set_collision_profile_name(profile)
    for actor in list(existing.values()):
        if isinstance(actor, unreal.StaticMeshActor) and actor not in mesh_actors.values():
            if not ACTORS.destroy_actor(actor):
                raise RuntimeError(f"Could not remove obsolete generated actor {actor.get_actor_label()}")
    place_instanced_props(existing, package.get("props", {}).get("instances", {}))
    road_edge_structs, vehicle_structs, traffic_seed = place_traffic_network(
        existing, package.get("road-graph"), package.get("traffic_network"), package.get("vehicle"),
    )
    place_citizens(existing, package.get("citizens"), road_edge_structs, vehicle_structs, traffic_seed)

    start = ue_position(package["start_m"])
    first, second = (ue_position([*point, 0]) for point in package["reference_points_m"])
    yaw = degrees(atan2(second.y - first.y, second.x - first.x))
    place(existing, "Player Start - Goethestrasse", unreal.PlayerStart, start, unreal.Rotator(yaw=yaw))
    reference_a = place(existing, "Goethestrasse - Reference A", unreal.TargetPoint, first)
    reference_b = place(existing, "Goethestrasse - Reference B", unreal.TargetPoint, second)
    distance_m = (reference_b.get_actor_location() - reference_a.get_actor_location()).length() / 100
    error = abs(distance_m / package["reference_geodesic_m"] - 1)
    if error > package["maximum_relative_error"]:
        raise RuntimeError(f"In-editor reference distance out of tolerance: {distance_m:.4f} m")

    sun = place(existing, "Altstadt Sun", unreal.DirectionalLight, unreal.Vector(),
                unreal.Rotator(pitch=-53, yaw=-58))
    sun_component = sun.get_component_by_class(unreal.DirectionalLightComponent)
    sun_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun_component.set_intensity(3.5)
    sun_component.set_editor_property("atmosphere_sun_light", True)
    place(existing, "Altstadt Sky", unreal.SkyAtmosphere, unreal.Vector())
    skylight = place(existing, "Altstadt Skylight", unreal.SkyLight, unreal.Vector())
    sky_component = skylight.get_component_by_class(unreal.SkyLightComponent)
    sky_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sky_component.set_intensity(1.3)
    sky_component.set_editor_property("real_time_capture", True)

    street_lights = []
    lamp_positions = package.get("props", {}).get("lamp_lights_m", [])
    active_lamp_labels = set()
    for index, pos_m in enumerate(lamp_positions):
        label = f"Altstadt StreetLight {index:02d}"
        active_lamp_labels.add(label)
        lamp_actor = place(existing, label, unreal.PointLight, ue_position(pos_m))
        lamp_comp = lamp_actor.get_component_by_class(unreal.PointLightComponent)
        lamp_comp.set_mobility(unreal.ComponentMobility.MOVABLE)
        lamp_comp.set_light_color(unreal.LinearColor(1.0, 0.78, 0.42, 1.0))
        lamp_comp.set_attenuation_radius(950.0)
        lamp_comp.set_cast_shadows(False)
        lamp_comp.set_intensity(0.0)
        street_lights.append(lamp_actor)
    for label, actor in list(existing.items()):
        if label.startswith("Altstadt StreetLight ") and label not in active_lamp_labels:
            if not ACTORS.destroy_actor(actor):
                raise RuntimeError(f"Could not remove obsolete street light {label}")

    day_night_class = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzDayNightController")
    if not day_night_class:
        raise RuntimeError("Build the DoemitzLivingCityEditor target before importing the day/night controller")
    day_night = place(existing, "Altstadt Day Night Controller", day_night_class, unreal.Vector())
    day_night.set_editor_property("sun_light", sun)
    day_night.set_editor_property("sky_light", skylight)
    day_night.set_editor_property("street_lights", street_lights)

    direction = second - first
    credit = start + unreal.Vector(0, 0, 235) + direction * (450 / direction.length())
    text_actor = place(existing, "OpenStreetMap Attribution", unreal.TextRenderActor, credit,
                       unreal.Rotator(yaw=yaw + 180))
    text_component = text_actor.get_component_by_class(unreal.TextRenderComponent)
    text_component.set_text(f"{package['attribution']}\nopenstreetmap.org/copyright")
    text_component.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
    text_component.set_world_size(14)

    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    roof = ue_position(package["roof_probe_m"])
    for ray_start, ray_end, surface in (
        (start, start - unreal.Vector(z=150), "terrain"),
        (roof + unreal.Vector(z=17000), roof + unreal.Vector(z=100), "roof"),
        (start, roof + unreal.Vector(z=100), "wall"),
    ):
        hit = unreal.SystemLibrary.line_trace_single(
            world, ray_start, ray_end,
            unreal.TraceTypeQuery.ECC_VISIBILITY, False, [], unreal.DrawDebugTrace.NONE, False
        )
        if hit is None:
            raise RuntimeError(f"Collision test did not hit the {surface}")

    sidewalk = package.get("sidewalk_probe_m")
    if sidewalk:
        point = ue_position(sidewalk)
        offset = unreal.Vector(z=100)
        hit = unreal.SystemLibrary.line_trace_single(
            world, point + offset, point - offset,
            unreal.TraceTypeQuery.ECC_VISIBILITY, False, [], unreal.DrawDebugTrace.NONE, False
        )
        if hit is None:
            raise RuntimeError("Sidewalk collision test missed")
        result = hit.to_dict()
        if result["hit_actor"] != mesh_actors["Sidewalks"] or abs(result["impact_point"].z - point.z) > 1:
            raise RuntimeError(f"Sidewalk collision test hit the wrong surface: {result}")

    # World Partition actors are separate content packages.
    if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
        raise RuntimeError(f"Could not save {MAP}")
    sidewalk_result = ", sidewalk collision passed" if sidewalk else ""
    unreal.log(
        f"DOEMITZ_IMPORT_OK: {len(assets)} meshes, {distance_m:.4f} m reference, "
        f"{error:.4%} error, terrain, roof and wall collision passed{sidewalk_result}"
    )


with PACKAGE.open(encoding="utf-8") as file:
    import_level(json.load(file))
