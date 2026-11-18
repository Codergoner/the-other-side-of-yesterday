"""Isolated desktop keyboard-test map; original Home maps and user saves stay intact."""
from pathlib import Path
import json
import unreal

root=Path(unreal.Paths.project_dir()).resolve()
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assert levels.load_level('/Game/Home/Maps/House_FirstPerson')
destination='/Game/Opening/Tests/InputSmoke_FirstPerson'
assert unreal.EditorLoadingAndSavingUtils.save_map(editor.get_editor_world(),destination)
assert levels.load_level(destination)
manager=next(a for a in actors.get_all_level_actors() if a.actor_has_tag('Opening.Manager'))
manager.set_editor_property('SaveSlot','Yesterday_InputSmoke_A_20261024_1')
for actor in actors.get_all_level_actors():
    if isinstance(actor,unreal.PlayerStart):
        actor.set_actor_location(unreal.Vector(-620,1370,1107),False,True)
        actor.set_actor_rotation(unreal.Rotator(pitch=-20,yaw=180,roll=0),True)
assert levels.save_current_level()
(root/'opening_input_test_map.json').write_text(json.dumps({'map':destination,'slot':manager.get_editor_property('SaveSlot'),'source_home_unchanged':True},indent=2))
