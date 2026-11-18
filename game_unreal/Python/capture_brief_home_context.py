"""A wider eye-level pair, preserving the full M1 multi-view report."""
from pathlib import Path
import sys
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(ROOT/'Python'))
import capture_brief_art as capture_module
from capture_brief_art import ArtCapture,BEFORE_MAP,AFTER_MAP

view={'id':'HomeFrontage','xy':[180,2100],'ground':'street',
      'target':[-680,1320,1370],'fov':85}
session=ArtCapture()
capture_module.VIEWS=[view]
session.report_path=ROOT/'brief_home_context_render_report.json'
session.report['scope']='Wider native eye-level home context before/after pair; no gameplay assertion'
session.groups=[
    {'label':'Before','map':BEFORE_MAP,'era':'Present','jobs':[(view,'Lit')]},
    {'label':'After','map':AFTER_MAP,'era':'Present','jobs':[(view,'Lit'),(view,'BaseColor')]},
]
session.start()
