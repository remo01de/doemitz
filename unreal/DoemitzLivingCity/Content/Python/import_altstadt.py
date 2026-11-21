"""Create or update the generated Altstadt level from the offline mesh package."""

import json
from math import atan2, degrees
from pathlib import Path

import unreal
from doemitz_citizen_mesh import stylized_citizen
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


def material(name, color):
    path = f"{ASSETS}/M_{name}"
    asset = EDITOR.load_asset(path) if EDITOR.does_asset_exist(path) else None
    if asset is None:
        asset = TOOLS.create_asset(f"M_{name}", ASSETS, unreal.Material, unreal.MaterialFactoryNew())
        expression_type = unreal.MaterialExpressionVertexColor if color is None else unreal.MaterialExpressionConstant3Vector
        base = unreal.MaterialEditingLibrary.create_material_expression(asset, expression_type, -300, 0)
        if color is not None:
            base.set_editor_property("constant", unreal.LinearColor(*color, 1))
        unreal.MaterialEditingLibrary.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
        roughness = unreal.MaterialEditingLibrary.create_material_expression(
            asset, unreal.MaterialExpressionConstant, -300, 150
        )
        roughness.set_editor_property("r", 0.85)
        unreal.MaterialEditingLibrary.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)
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


def place_citizens(existing, config):
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
    for actor in existing.values():
        if isinstance(actor, unreal.StaticMeshActor) and actor not in mesh_actors.values():
            if not ACTORS.destroy_actor(actor):
                raise RuntimeError(f"Could not remove obsolete generated actor {actor.get_actor_label()}")
    place_vehicle(existing, package.get("vehicle"))
    place_citizens(existing, package.get("citizens"))

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
