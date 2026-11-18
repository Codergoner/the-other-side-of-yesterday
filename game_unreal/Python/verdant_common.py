"""Shared helpers for the Verdant environment jobs. Everything lives under /Game/Verdant."""
import json
import math
from pathlib import Path

import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
RELEASE = PROJECT.parent
if RELEASE.name != 'Release_20261026':
    raise RuntimeError('Verdant jobs run only in the Release copy')
SOURCE = RELEASE / 'output' / 'verdant'
EVIDENCE = PROJECT / 'validation' / 'verdant'
EVIDENCE.mkdir(parents=True, exist_ok=True)
ROOT_PATH = '/Game/Verdant'
MAP = ROOT_PATH + '/Maps/Verdant_City'

# Direction toward the sun in Blender metres: azimuth from +Y toward +X, elevation.
SUN = {'Past': {'azimuth': 62.0, 'elevation': 13.0}, 'Present': {'azimuth': 66.0, 'elevation': 10.5}}

assets = unreal.AssetToolsHelpers.get_asset_tools()
library = unreal.EditorAssetLibrary
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def log(*parts):
    unreal.log('VERDANT ' + ' '.join(str(p) for p in parts))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def has_flag(name):
    return ('-' + name.lower()) in unreal.SystemLibrary.get_command_line().lower()


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')


def to_unreal(p):
    """Blender metres to Unreal centimetres; the FBX export mirrors Y the same way."""
    return unreal.Vector(p[0] * 100, -p[1] * 100, p[2] * 100)


def sun_rotation(era):
    a, e = math.radians(SUN[era]['azimuth']), math.radians(SUN[era]['elevation'])
    forward = (-math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), -math.sin(e))
    return unreal.Rotator(pitch=math.degrees(math.asin(forward[2])),
                          yaw=math.degrees(math.atan2(forward[1], forward[0])), roll=0)


def add_component(actor, cls, name):
    """Adds a real instance component that serialises with the actor."""
    sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = sub.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    handle, reason = sub.add_new_subobject(params)
    require(handle is not None, 'Subobject failed: ' + str(reason))
    sub.rename_subobject(handle, unreal.Text(name))
    data = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(handle)
    component = unreal.SubobjectDataBlueprintFunctionLibrary.get_object(data)
    require(component is not None, 'No component object for ' + name)
    return component
