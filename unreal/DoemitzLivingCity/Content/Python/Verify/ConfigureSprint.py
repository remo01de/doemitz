import unreal


assets = unreal.EditorAssetLibrary
blueprints = unreal.BlueprintEditorLibrary
character = assets.load_asset("/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter")
mapping = assets.load_asset("/Game/Input/IMC_Default")
native_character = unreal.load_class(None, "/Script/DoemitzLivingCity.DoemitzCharacter")
if not all((character, mapping, native_character)):
    raise RuntimeError("Could not load the character Blueprint, input context or native class")

action = assets.load_asset("/Game/Input/Actions/IA_Sprint")
if action is None:
    action = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "IA_Sprint", "/Game/Input/Actions", unreal.InputAction, unreal.InputAction_Factory()
    )
if action is None:
    raise RuntimeError("Could not create IA_Sprint")
action.set_editor_property("value_type", unreal.InputActionValueType.BOOLEAN)

key = unreal.Key()
key.import_text("LeftShift")
if key.export_text() != "LeftShift":
    raise RuntimeError(f"Could not resolve LeftShift: {key.export_text()}")
mapping.unmap_all_keys_from_action(action)
mapping.map_key(action, key)

blueprints.reparent_blueprint(character, native_character)
if not blueprints.compile_blueprint(character):
    raise RuntimeError("Could not compile BP_ThirdPersonCharacter")
generated_class = blueprints.generated_class(character)
character_defaults = unreal.get_default_object(generated_class)
character_defaults.set_editor_property("sprint_action", action)

for asset in (action, mapping, character):
    if not assets.save_loaded_asset(asset, only_if_is_dirty=False):
        raise RuntimeError(f"Could not save {asset.get_path_name()}")

unreal.log("DOEMITZ_SPRINT_ASSETS_OK")
