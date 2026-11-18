"""Read-only M1 before/after art captures in the actual Unreal editor.

SceneCapture2D renders transient RGBA8/gamma-2.2 targets. No map, asset,
configuration, campaign flag, inventory or save-slot write is performed.
Past shots are explicitly editor visibility previews, never gameplay proof.
Run only in a dedicated editor process after build_brief_art has completed.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
import time
import traceback
import unreal

ROOT=Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0,str(ROOT/'Python'))
import harbor_lighting
import release_file_io as long_io

BEFORE_MAP='/Game/Home/Maps/House_FirstPerson'
AFTER_MAP='/Game/BriefTest/Maps/Quarter_FirstPerson'
WIDTH,HEIGHT=1600,900
EYE_HEIGHT_CM=162.0
VIEWS=[
    {'id':'HomeFrontage','xy':[100,1800],'ground':'street','target':[-650,1300,1320],'fov':74},
    {'id':'UphillCathedral','xy':[0,1100],'ground':'street','target':[-100,-4000,1600],'fov':74},
    {'id':'SurvivingRoom','xy':[-620,1240],'ground':'house','target':[-950,1360,1150],'fov':82},
    {'id':'ClinicApproach','xy':[100,550],'ground':'street','target':[-410,550,1090],'fov':76},
    {'id':'HarborShelter','xy':[0,-700],'ground':'street','target':[230,-650,1240],'fov':76},
    # The verified porch point is used rather than (-150,1600,1170), which
    # would be over 3 m above the street's analytic floor, not eye level.
    {'id':'Archive','xy':[-245,1510],'ground':'house','target':[-350,1460,1160],'fov':94},
]
OUTCOME_TAGS=['Opening.ClinicCover','Opening.HarborCover','Opening.ClinicRecord','Opening.HarborRecord']
CVARS=['r.DynamicGlobalIlluminationMethod','r.ReflectionMethod','r.Shadow.Virtual.Enable',
       'r.Nanite','r.RayTracing','r.ScreenPercentage','t.MaxFPS','r.VSync']


def xyz(value):return [round(value.x,3),round(value.y,3),round(value.z,3)]
def digest(path):return long_io.sha(path)


class ArtCapture:
    def __init__(self):
        self.level=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
        self.folder=ROOT/'validation'/'brief_art'/self.stamp
        self.folder.mkdir(parents=True,exist_ok=False)
        self.report_path=ROOT/'brief_art_render_report.json'
        self.report={'success':False,'run':self.stamp,
            'scope':'Native editor art review; no PIE, packaged-game or headset assertion',
            'renderer':'SceneCapture2D FinalColorLDR -> RGBA8 target, gamma 2.2',
            'resolution':[WIDTH,HEIGHT],'source_map':BEFORE_MAP,'test_map':AFTER_MAP,
            'camera_policy':'Before/after pairs share fixed world position, target, horizontal FOV and manual capture exposure.',
            'ground_policy':'Street-center floor Zcm=1020-0.1*Ycm; house/porch floor Zcm=896+115=1011. Visibility line traces cross-check each point.',
            'eye_height_cm':EYE_HEIGHT_CM,'images':[],'pixel_samples':[],
            'view_coordinates':{},'era_previews':[],'diagnostics':[],
            'warnings':[],'cleanup_errors':[],
            'gameplay_tested':False,'story_flags_modified':False,'save_profiles_written':False,
            'asset_save_calls':False,'references_projected':False}
        self.groups=[
            {'label':'Before','map':BEFORE_MAP,'era':'Present','jobs':[(v,'Lit') for v in VIEWS]},
            {'label':'After','map':AFTER_MAP,'era':'Present','jobs':[(v,'Lit') for v in VIEWS]+[(VIEWS[0],mode) for mode in ['BaseColor','LightingOnly']]},
            {'label':'After','map':AFTER_MAP,'era':'Past','jobs':[(VIEWS[i],'Lit') for i in [0,3,4]],'optional':True},
        ]
        self.group_index=0;self.job_index=0;self.phase='load';self.phase_time=time.monotonic()
        self.frame_count=0;self.handle=None;self.finished=False
        self.world=None;self.capture=None;self.component=None;self.target=None
        self.visibility=[];self.cvar_restore={};self.fixed_views={};self.default_flags=None
        self.protected={}
        for package in [BEFORE_MAP,AFTER_MAP]:
            path=ROOT/'Content'/(package.removeprefix('/Game/')+'.umap')
            if not path.is_file():raise RuntimeError('Required saved art map is missing: '+str(path))
            self.protected[path]=digest(path)
        for path in [ROOT/'YesterdayHarbor.uproject',*(ROOT/'Config').glob('*.ini')]:
            self.protected[path]=digest(path)

    def write(self):
        self.report['active']={'group':self.group_index,'job':self.job_index,'phase':self.phase}
        temporary=self.report_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(self.report,indent=2,default=str),encoding='utf-8')
        temporary.replace(self.report_path)

    def metadata(self):
        result={'engine':unreal.SystemLibrary.get_engine_version(),
                'platform':unreal.GameplayStatics.get_platform_name(),
                'console_values':{},'startup_log_metadata':{},'startup_log':None,
                'actual_gpu_verified':False,'actual_rhi_verified':False}
        for name in CVARS:
            try:result['console_values'][name]=unreal.SystemLibrary.get_console_variable_string_value(name)
            except Exception as error:result['console_values'][name]={'unavailable':str(error)}
        command=unreal.SystemLibrary.get_command_line()
        match=re.search(r'(?i)(?:^|\s)-abslog=(?:"([^"]+)"|(\S+))',command)
        candidates=[Path(match.group(1) or match.group(2))] if match else []
        logdir=ROOT/'Saved'/'Logs'
        if logdir.exists():candidates+=sorted(logdir.glob('*.log'),key=lambda p:p.stat().st_mtime,reverse=True)[:3]
        for path in candidates:
            if not path.is_file() or path.stat().st_mtime < time.time()-300:continue
            text=path.read_text(encoding='utf-8',errors='replace')
            values=dict(re.findall(r'Metadata set\s*:\s*(\w+)="([^"]*)"',text))
            selected={key:values[key] for key in ['gpu','rhiname','verbatimrhiname','rhifeaturelevel','shaderplatform','gpudriver','driverinternalversion','driverversion'] if values.get(key)}
            if selected:
                result['startup_log']=str(path);result['startup_log_metadata']=selected
                result['actual_gpu_verified']=bool(selected.get('gpu'))
                result['actual_rhi_verified']=bool(selected.get('rhiname') or selected.get('verbatimrhiname'))
                break
        if not result['actual_gpu_verified']:result['gpu_note']='Active GPU unavailable in fresh startup log; no CPU-based GPU inference.'
        if not result['actual_rhi_verified']:result['rhi_note']='Active RHI unavailable in fresh startup log; configured RHI is not treated as runtime proof.'
        allowed={'DefaultGraphicsRHI','D3D12TargetedShaderFormats','D3D11TargetedShaderFormats',
                 'r.DynamicGlobalIlluminationMethod','r.ReflectionMethod','r.Shadow.Virtual.Enable',
                 'r.GenerateMeshDistanceFields','r.AllowStaticLighting'}
        config={}
        for line in (ROOT/'Config'/'DefaultEngine.ini').read_text(encoding='utf-8-sig').splitlines():
            key,sep,value=line.lstrip('+').partition('=')
            if sep and key in allowed:config.setdefault(key,[]).append(value)
        result['configured_graphics_only']=config
        return result

    def set_session_cvars(self):
        for name,value in [('t.IdleWhenNotForeground','0'),('Slate.bAllowThrottling','0'),('r.ScreenPercentage','100')]:
            previous=unreal.SystemLibrary.get_console_variable_string_value(name)
            if previous!='':self.cvar_restore[name]=previous
            unreal.SystemLibrary.execute_console_command(self.world,name+' '+value)
        self.report['temporary_console_overrides']={'t.IdleWhenNotForeground':'0','Slate.bAllowThrottling':'0','r.ScreenPercentage':'100'}

    def apply_era_preview(self,era):
        selected=[]
        for actor in self.actors.get_all_level_actors():
            past=actor.actor_has_tag('Opening.PastOnly');present=actor.actor_has_tag('Opening.PresentOnly')
            outcome=any(actor.actor_has_tag(tag) for tag in OUTCOME_TAGS)
            if not (past or present or outcome):continue
            snapshot={'actor':actor,'hidden':bool(actor.get_editor_property('hidden'))}
            if hasattr(actor,'is_temporarily_hidden_in_editor'):
                snapshot['editor_hidden']=bool(actor.is_temporarily_hidden_in_editor())
            self.visibility.append(snapshot)
            show=(past if era=='Past' else present) and not outcome
            actor.set_actor_hidden_in_game(not show)
            if 'editor_hidden' in snapshot and hasattr(actor,'set_is_temporarily_hidden_in_editor'):
                actor.set_is_temporarily_hidden_in_editor((not show) or snapshot['editor_hidden'])
            selected.append({'actor':actor.get_name(),'visible':show,'past_tag':past,'present_tag':present,'outcome_hidden':outcome})
        record={'map':self.groups[self.group_index]['map'],'era':era,
            'method':'Temporary actor visibility only; no story state, collision, NPC location, save or quest transaction changes.',
            'outcome_covers_and_pages':'Hidden in every preview; no canvas decision is simulated.',
            'actors':selected}
        self.report['era_previews'].append(record)
        return any(row['past_tag'] for row in selected)

    def restore_world(self):
        if self.capture is not None:
            try:self.actors.destroy_actor(self.capture)
            except Exception:self.report['cleanup_errors'].append(traceback.format_exc())
        if self.target is not None and hasattr(unreal.RenderingLibrary,'release_render_target2d'):
            try:unreal.RenderingLibrary.release_render_target2d(self.target)
            except Exception:self.report['cleanup_errors'].append(traceback.format_exc())
        self.capture=None;self.component=None;self.target=None
        for snapshot in self.visibility:
            try:
                actor=snapshot['actor'];actor.set_actor_hidden_in_game(snapshot['hidden'])
                if 'editor_hidden' in snapshot:actor.set_is_temporarily_hidden_in_editor(snapshot['editor_hidden'])
            except Exception:self.report['cleanup_errors'].append(traceback.format_exc())
        self.visibility=[]

    def ground(self,spec):
        x,y=spec['xy'];hint=1011.0 if spec['ground']=='house' else 1020.0-.1*y
        record={'hint_cm':hint,'formula':'House/porch 896+115' if spec['ground']=='house' else 'Street center 1020-0.1*Y',
                'method':'Verified authored floor; visibility trace unavailable','trace':None}
        try:
            ignored=[a for a in self.actors.get_all_level_actors() if isinstance(a,unreal.SkeletalMeshActor)]
            if self.capture:ignored.append(self.capture)
            hit=unreal.SystemLibrary.line_trace_single(self.world,unreal.Vector(x,y,hint+80),unreal.Vector(x,y,hint-1000),
                unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,ignored,unreal.DrawDebugTrace.NONE,True)
            values=hit.to_tuple();point=values[5];actor=values[9]
            static_component=actor.get_component_by_class(unreal.StaticMeshComponent) if actor else None
            static_mesh=static_component.get_editor_property('static_mesh') if static_component else None
            record['trace']={'blocking':bool(values[0]),'impact_cm':xyz(point),'actor':actor.get_actor_label() if actor else None,
                'static_mesh':static_mesh.get_name() if static_mesh else None}
            if values[0] and abs(point.z-hint)<=40:
                record['method']='Visibility trace checked against authored floor';return float(point.z),record
            record['method']='Verified authored floor; trace did not identify a nearby ground surface'
        except Exception as error:record['trace_error']=str(error)
        return hint,record

    def resolved_view(self,spec):
        ground,record=self.ground(spec)
        if spec['id']=='HomeFrontage':
            trace=record.get('trace') or {}
            if record['method']!='Visibility trace checked against authored floor' or trace.get('static_mesh') not in ['SM_StreetFoundation','SM_StreetSurface']:
                raise RuntimeError('Home-frontage eye level requires an actual promenade ground hit; refusing formula-only capture: '+json.dumps(record))
        if spec['id'] not in self.fixed_views:
            position=[spec['xy'][0],spec['xy'][1],ground+EYE_HEIGHT_CM]
            self.fixed_views[spec['id']]={'position_cm':position,'target_cm':spec['target'],'horizontal_fov':spec['fov'],
                'reference_ground_cm':ground,'reference_ground_measurement':record}
            self.report['view_coordinates'][spec['id']]=self.fixed_views[spec['id']]
        fixed=self.fixed_views[spec['id']]
        return fixed,{'ground_cm':ground,'measurement':record,'eye_height_above_current_ground_cm':fixed['position_cm'][2]-ground}

    def flags(self,values):
        flag_type=getattr(unreal,'EngineShowFlagsSetting',None)
        if flag_type is None:raise RuntimeError('EngineShowFlagsSetting is not exposed by the installed Python API')
        result=[]
        for name,enabled in values:
            setting=flag_type();setting.set_editor_property('show_flag_name',name);setting.set_editor_property('enabled',enabled);result.append(setting)
        if hasattr(self.component,'set_show_flag_settings'):self.component.set_show_flag_settings(result)
        else:self.component.set_editor_property('show_flag_settings',result)
        actual=self.component.get_show_flag_settings() if hasattr(self.component,'get_show_flag_settings') else self.component.get_editor_property('show_flag_settings')
        observed={str(setting.get_editor_property('show_flag_name')):bool(setting.get_editor_property('enabled')) for setting in actual}
        if any(observed.get(name)!=enabled for name,enabled in values):raise RuntimeError('Native capture show-flag settings did not retain requested values')
        return observed

    def configure_mode(self,mode):
        try:
            if self.default_flags is not None:
                if hasattr(self.component,'set_show_flag_settings'):self.component.set_show_flag_settings(self.default_flags)
                else:self.component.set_editor_property('show_flag_settings',self.default_flags)
            self.component.set_editor_property('capture_source',unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
            if mode=='BaseColor':self.component.set_editor_property('capture_source',unreal.SceneCaptureSource.SCS_BASE_COLOR)
            elif mode=='LightingOnly':self.flags([('Lighting',True),('Materials',False),('LightingOnlyOverride',True)])
            if mode!='Lit':self.report['diagnostics'].append({'mode':mode,'supported':True,'mechanism':'Native scene capture source' if mode=='BaseColor' else 'Native EngineShowFlagsSetting; Lighting / Materials / LightingOnlyOverride'})
            return True
        except Exception as error:
            if mode=='Lit':raise
            self.report['diagnostics'].append({'mode':mode,'supported':False,'reason':str(error)})
            return False

    def load_group(self):
        self.restore_world();group=self.groups[self.group_index]
        if not self.level.load_level(group['map']):raise RuntimeError('Cannot load saved art map '+group['map'])
        self.world=self.editor.get_editor_world()
        if not self.cvar_restore:self.set_session_cvars()
        has_past=self.apply_era_preview(group['era'])
        if group.get('optional') and not has_past:
            self.report['warnings'].append('Past art preview skipped: no explicit PastOnly actors in saved test map.')
            self.next_group();return
        self.capture=self.actors.spawn_actor_from_class(unreal.SceneCapture2D,unreal.Vector(0,0,0),unreal.Rotator(pitch=0,yaw=0,roll=0),True)
        self.capture.set_actor_label('Brief temporary art capture — never save')
        self.component=self.capture.get_component_by_class(unreal.SceneCaptureComponent2D)
        self.target=unreal.RenderingLibrary.create_render_target2d(self.world,WIDTH,HEIGHT,unreal.TextureRenderTargetFormat.RTF_RGBA8,unreal.LinearColor(1,0,1,1),False,False)
        self.target.set_editor_property('target_gamma',2.2)
        for key,value in [('texture_target',self.target),('capture_every_frame',False),('capture_on_movement',False),('always_persist_rendering_state',True)]:self.component.set_editor_property(key,value)
        self.component.set_editor_property('post_process_settings',harbor_lighting.exposure(self.component.get_editor_property('post_process_settings')))
        self.component.set_editor_property('post_process_blend_weight',1.0)
        try:self.default_flags=list(self.component.get_show_flag_settings() if hasattr(self.component,'get_show_flag_settings') else self.component.get_editor_property('show_flag_settings'))
        except Exception:self.default_flags=None
        self.phase='configure';self.phase_time=time.monotonic();self.write()

    def next_group(self):
        self.group_index+=1;self.job_index=0
        if self.group_index>=len(self.groups):self.finish();return
        self.phase='load';self.phase_time=time.monotonic();self.write()

    def configure_view(self):
        group=self.groups[self.group_index]
        if self.job_index>=len(group['jobs']):self.next_group();return
        spec,mode=group['jobs'][self.job_index]
        if not self.configure_mode(mode):self.job_index+=1;return
        unreal.AutomationLibrary.finish_loading_before_screenshot()
        fixed,ground=self.resolved_view(spec)
        position,target=unreal.Vector(*fixed['position_cm']),unreal.Vector(*fixed['target_cm'])
        self.capture.set_actor_location(position,False,False)
        self.capture.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(position,target),False)
        self.component.set_editor_property('fov_angle',fixed['horizontal_fov'])
        self.current={'label':group['label'],'era':group['era'],'map':group['map'],'view':spec['id'],'mode':mode,
            **fixed,'current_ground_check':ground,'editor_art_preview':True}
        if mode=='BaseColor':self.current['diagnostic_purpose']='Unlit material base-color/albedo buffer; not a gameplay lighting view.'
        elif mode=='LightingOnly':self.current['diagnostic_purpose']='Native lighting-only show flags with material response overridden for diagnosis.'
        if abs(ground['eye_height_above_current_ground_cm']-EYE_HEIGHT_CM)>8:
            self.report['warnings'].append({'view':spec['id'],'map':group['map'],'ground_changed_between_pairs':ground})
        self.frame_count=0;self.phase='warm';self.phase_time=time.monotonic();self.write()

    def export(self):
        colors=[]
        for yf in [.1,.3,.5,.7,.9]:
            for xf in [.1,.25,.5,.75,.9]:
                color=unreal.RenderingLibrary.read_render_target_pixel(self.world,self.target,int(WIDTH*xf),int(HEIGHT*yf))
                colors.append((int(color.r),int(color.g),int(color.b)))
        values=[value for color in colors for value in color];mean=sum(values)/len(values)
        pixel={'view':self.current['view'],'label':self.current['label'],'era':self.current['era'],'mode':self.current['mode'],
            'min':min(values),'max':max(values),'mean':mean,'variance':sum((value-mean)**2 for value in values)/len(values),
            'unique_colors':len(set(colors)),'samples':colors}
        self.report['pixel_samples'].append(pixel)
        if pixel['max']<8 or pixel['variance']<2 or pixel['unique_colors']<4:raise RuntimeError('Native capture contains no usable image content: '+str(pixel))
        if self.current['view']=='SurvivingRoom' and (mean<25 or pixel['max']<70):raise RuntimeError('Actual room capture is too dark for the existing readability gate: '+str(pixel))
        filename='_'.join(self.current[key] for key in ['label','era','view','mode'])+'.png'
        unreal.RenderingLibrary.export_render_target(self.world,self.target,str(self.folder),filename)
        output=self.folder/filename
        if not output.is_file() or output.stat().st_size<50000:raise RuntimeError('Native PNG export failed: '+str(output))
        self.report['images'].append({**self.current,'path':str(output),'bytes':output.stat().st_size,'warm_frames':self.frame_count})
        self.job_index+=1;self.phase='configure';self.phase_time=time.monotonic();self.write()

    def finish(self,error=None):
        if self.finished:return
        self.finished=True
        if error:self.report['error']=error
        self.restore_world()
        for name,value in self.cvar_restore.items():
            try:unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(),name+' '+value)
            except Exception:self.report['cleanup_errors'].append(traceback.format_exc())
        self.report['runtime_metadata']=self.metadata()
        changed=[str(path) for path,before in self.protected.items() if not long_io.is_file(path) or digest(path)!=before]
        self.report['protected_maps_and_config_unchanged']=not changed;self.report['unexpected_file_changes']=changed
        required={(label,spec['id']) for label in ['Before','After'] for spec in VIEWS}
        captured={(row['label'],row['view']) for row in self.report['images'] if row['era']=='Present' and row['mode']=='Lit'}
        self.report['required_present_pairs_complete']=required.issubset(captured)
        self.report['base_color_or_unlit_diagnostic_complete']=any(row['mode'] in ['BaseColor','Unlit'] for row in self.report['images'])
        self.report['success']=not error and not changed and not self.report['cleanup_errors'] and required.issubset(captured) and self.report['base_color_or_unlit_diagnostic_complete']
        self.phase='finished';self.write()
        if self.handle is not None:unreal.unregister_slate_post_tick_callback(self.handle)
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()

    def tick(self,delta):
        if self.finished:return
        try:
            elapsed=time.monotonic()-self.phase_time
            if elapsed>120:raise TimeoutError('Art capture phase timed out: '+self.phase)
            if self.phase=='load':self.load_group()
            elif self.phase=='configure':self.configure_view()
            elif self.phase=='warm':
                self.component.capture_scene();self.frame_count+=1
                if self.frame_count>=24 and elapsed>=2.0:self.export()
        except Exception:self.finish(traceback.format_exc())

    def start(self):
        if self.level.is_in_play_in_editor():raise RuntimeError('Art review must run outside PIE; no gameplay flags will be used.')
        unreal.EditorPythonScripting.set_keep_python_script_alive(True)
        self.report['runtime_metadata']=self.metadata();self.write()
        self.handle=unreal.register_slate_post_tick_callback(self.tick)


def main():
    session=None
    try:
        session=ArtCapture();session.start()
    except Exception:
        error=traceback.format_exc()
        if session is not None:session.finish(error)
        else:
            (ROOT/'brief_art_render_report.json').write_text(json.dumps({'success':False,'scope':'Native editor art capture setup','error':error},indent=2),encoding='utf-8')
            unreal.EditorPythonScripting.set_keep_python_script_alive(False);unreal.SystemLibrary.quit_editor()


if __name__=='__main__':main()
