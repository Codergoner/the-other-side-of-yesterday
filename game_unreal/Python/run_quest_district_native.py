"""Single queued native district authoring run; always close its hidden editor."""
import traceback
import sys
from pathlib import Path
import unreal
sys.path.insert(0,str(Path(__file__).resolve().parent))
try:
    import build_quest_district
    report=build_quest_district.build_district()
    unreal.log('QUEST_DISTRICT_NATIVE_SUCCESS '+str(report['success']))
except Exception:
    unreal.log_error('QUEST_DISTRICT_NATIVE_FAILED\n'+traceback.format_exc())
finally:
    unreal.SystemLibrary.quit_editor()
