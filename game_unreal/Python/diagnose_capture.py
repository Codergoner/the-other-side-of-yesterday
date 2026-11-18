from pathlib import Path
import json,time,traceback
import unreal
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
ROOT=Path(unreal.Paths.project_dir()).resolve()
LEVEL=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ACTORS=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVEL.load_level('/Game/Harbor/Maps/Harbor_ThirdPerson')
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
for cmd in ['t.IdleWhenNotForeground 0','Slate.bAllowThrottling 0']:
    unreal.SystemLibrary.execute_console_command(world,cmd)
capture=ACTORS.spawn_actor_from_class(unreal.SceneCapture2D,unreal.Vector(300,3500,1700),unreal.MathLibrary.find_look_at_rotation(unreal.Vector(300,3500,1700),unreal.Vector(1400,-4500,1500)),True)
comp=capture.get_component_by_class(unreal.SceneCaptureComponent2D)
rt=unreal.RenderingLibrary.create_render_target2d(world,800,500,unreal.TextureRenderTargetFormat.RTF_RGBA8,unreal.LinearColor(1,0,1,1),False,False)
for key,val in [('texture_target',rt),('capture_every_frame',False),('capture_on_movement',False),('always_persist_rendering_state',True),('fov_angle',65.47)]:comp.set_editor_property(key,val)
out={'world':world.get_path_name(),'capture_world':capture.get_world().get_path_name(),'actor_count':len(ACTORS.get_all_level_actors()),'lights':[],'tests':[]}
for actor in ACTORS.get_all_level_actors():
    if isinstance(actor,unreal.DirectionalLight):
        light=actor.get_component_by_class(unreal.DirectionalLightComponent)
        out['lights'].append({'name':actor.get_actor_label(),'intensity':light.get_editor_property('intensity'),'rotation':str(actor.get_actor_rotation())})
MODES=[('base_color',unreal.SceneCaptureSource.SCS_BASE_COLOR,None),('scene_color',unreal.SceneCaptureSource.SCS_SCENE_COLOR_HDR,None),('manual_0',unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,0.2),('manual_minus_8',unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,-8.5),('manual_minus_11',unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,-11.5)]
state={'index':0,'phase':'configure','frames':0,'time':time.monotonic()};handle=None
def finish():
    (ROOT/'capture_diagnostics.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.quit_editor()
def tick(dt):
    try:
        if state['phase']=='configure':
            name,source,bias=MODES[state['index']]
            comp.set_editor_property('capture_source',source)
            if bias is not None:
                pp=unreal.PostProcessSettings()
                for key,val in [('auto_exposure_method',unreal.AutoExposureMethod.AEM_MANUAL),('auto_exposure_apply_physical_camera_exposure',False),('auto_exposure_bias',bias)]:
                    pp.set_editor_property('override_'+key,True);pp.set_editor_property(key,val)
                comp.set_editor_property('post_process_settings',pp);comp.set_editor_property('post_process_blend_weight',1.0)
            comp.capture_scene();state.update(phase='capture',frames=0,time=time.monotonic())
        else:
            state['frames']+=1
            if state['frames']<20:comp.capture_scene()
            elif time.monotonic()-state['time']>1.0:
                colors=[]
                for y in [50,150,250,350,450]:
                    for x in [50,200,400,600,750]:
                        c=unreal.RenderingLibrary.read_render_target_pixel(world,rt,x,y);colors.append((int(c.r),int(c.g),int(c.b)))
                values=[v for c in colors for v in c];name=MODES[state['index']][0]
                record={'mode':name,'min':min(values),'max':max(values),'mean':sum(values)/len(values),'unique':len(set(colors)),'samples':colors}
                out['tests'].append(record)
                unreal.RenderingLibrary.export_render_target(world,rt,str(ROOT),'diagnostic_'+name+'.png')
                (ROOT/'capture_diagnostics.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
                state['index']+=1
                if state['index']>=len(MODES):finish()
                else:state['phase']='configure'
    except Exception:
        out['error']=traceback.format_exc();finish()
handle=unreal.register_slate_post_tick_callback(tick)
