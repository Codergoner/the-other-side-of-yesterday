"""The four-route v0.2 story acceptance with every player step issued through the Quest 3 pawn's hands-only layer.

Run with -ReleaseStoryQA -QuestStoryV2QA -Quest3XRStoryQA -Quest3HandsStoryQA and a fresh short -UserDir. It layers on
validate_quest3_story_xr.py (XR pawn, HMD-locked camera aiming, release ending gate) exactly as that file layers on the
v0.2 harness: the established text is loaded and only the harness's manager-action primitive changes. Player actions
(Interact, AdvanceDialogue, ChooseDialogue, SkipRecollections, FlipPhoto, CloseModal, CloseDocument, OpenPause,
OpenWatch, RotateDial, ConfirmWatch, OpenJournal, TurnJournal, HandleOne..Three, ReleaseSelect) are performed by
simulated fingertip positions driving the pawn's own pinch-distance, eye-to-pinch-ray and dispatch code; each is
checked against the pawn's QuestLastHandAction label. Anything the harness still issues directly (its fixtures and
test-only calls) is listed in the report as direct_manager_actions. Simulated fingertips, no hand-tracking hardware,
no headset, no controller or keyboard key.
"""
from pathlib import Path
import unreal

H_ROOT = Path(unreal.Paths.project_dir()).resolve()
if not unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3HandsStoryQA'):
    raise RuntimeError('Root-queued -Quest3HandsStoryQA is required')
H_PARENT_FILE = H_ROOT / 'Python/validate_quest3_story_xr.py'
H_PARENT = H_PARENT_FILE.read_text(encoding='utf-8')
H_ENDING = "exec(compile(source, str(X_ROOT / 'Python/validate_brief_m2.py'), 'exec'), globals())"
H_PREFIX, H_SEP, H_SUFFIX = H_PARENT.rpartition(H_ENDING)
if not H_SEP or H_SUFFIX.strip():
    raise RuntimeError('The XR story launch is no longer the checked final statement')
H_OLD_FILE = globals().get('__file__')
globals()['__file__'] = str(H_PARENT_FILE)
try:
    # Builds the reviewed XR-pawn harness text (which builds the v0.2 and release texts) and the unsaved fixtures;
    # registers no ticker and begins no gameplay until the final exec below.
    exec(compile(H_PREFIX, str(H_PARENT_FILE), 'exec'), globals())
finally:
    globals()['__file__'] = H_OLD_FILE


def h_replace(old, new, count=1):
    global source
    if source.count(old) != count:
        raise RuntimeError('Changed hands acceptance point (%d expected): %s' % (count, old[:140]))
    source = source.replace(old, new)


H_ACTION = '''H_HAND_STEPS=[]
H_DIRECT=[]
import math as h_math,sys as h_sys
if str(H_ROOT/'Python') not in h_sys.path:h_sys.path.insert(0,str(H_ROOT/'Python'))
import quest3_sim_hand as h_sim
# -Quest3OneHandLeftQA (12 November 2026): the same four routes played with the LEFT hand only, as a left-handed player
# with one usable hand. The pawn is told the main hand is the left; every pinch is made by the physical left hand; what
# the off hand does elsewhere is done on the Back and Menu buttons. The right hand is never tracked.
H_ONE=unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(),'Quest3OneHandLeftQA')
H_MAIN=not H_ONE
def h_pawn():return S['pawn']
def h_frame(delta=1.0/72.0):h_pawn().call_method('QuestHandsFrame',args=(delta,))
def h_point(point,right=True,pinched=True):
    p=h_pawn()
    if H_ONE:
        if right:raise AssertionError('The one-hand run moved the right hand')
        p.set_editor_property('QuestLeftHanded',True);p.set_editor_property('QuestMainChosen',True);p.set_editor_property('QuestSimRightValid',False)
    side='Right' if right else 'Left'
    p.set_editor_property('QuestSimHands',True);p.set_editor_property('QuestOnboardStep',0);p.set_editor_property('QuestAutoGazeEnabled',False);p.set_editor_property('QuestSim'+side+'Valid',True)
    thumb=point if pinched else point+unreal.Vector(0,0,-8)
    p.set_editor_property('QuestSim'+side+'Thumb',thumb);p.set_editor_property('QuestSim'+side+'Index',point)
    h_sim.place(p,right,point,thumb)
def h_dial_point(angle,radius=13.0):
    # A world point on the watch face (panel units: the dial centre is 42 cm right of the panel centre; +angle is the viewer's left).
    a=h_math.radians(angle);panel=h_pawn().get_editor_property('QuestPanelRoot')
    return unreal.MathLibrary.transform_location(panel.get_world_transform(),unreal.Vector(2.0,-42.0+h_math.sin(a)*radius,h_math.cos(a)*radius))
def h_dial(direction):
    # RotateDial by hand (12 November 2026): pinch the watch face on the selected era's side, carry the pinch round to the other
    # mark, let go. direction > 0 is the present (right mark), otherwise the past (left mark), as the manager's RotateDial.
    p=h_pawn();target=0 if direction>0 else 1
    start=50.0 if int(prop('SelectedEra'))==1 else -50.0;end=-50.0 if direction>0 else 50.0
    # The pawn tick runs QuestHandsFrame then QuestDialFrame every frame; both are called here in that order.
    h_point(h_dial_point(start),H_MAIN,False);h_frame();h_point(h_dial_point(start),H_MAIN,True);h_frame();p.call_method('QuestDialFrame',args=(1.0/72.0,))
    label=str(p.get_editor_property('QuestLastHandAction'));held=bool(p.get_editor_property('QuestDialHeld'))
    for i in range(1,9):
        h_point(h_dial_point(start+(end-start)*i/8.0),H_MAIN,True);h_frame();p.call_method('QuestDialFrame',args=(1.0/72.0,))
    angle=float(p.get_editor_property('QuestDialAngle'))
    h_point(h_dial_point(end),H_MAIN,False);h_frame(.4);p.call_method('QuestDialFrame',args=(.4,))
    # What the panel draws: the story's long dash is drawn as a plain one (the text-render font has no long dash).
    h_panel();drawn=str(p.get_editor_property('QuestPanelText').get_editor_property('text'));kept=str(p.get_editor_property('QuestCachedQuestPanelText'));plain=('\\u2014' not in drawn) and ('\\u2014' in kept) and drawn.count(' - ')>=kept.count(' \\u2014 ')
    # True watch readout (16 November 2026): nothing unavailable or locked is listed, the manager's CONFIRM line is replaced
    # by what Select will do from here, and in the past the home clock is drawn as minutes:seconds of ReturnClockSeconds.
    away=int(float(prop('ReturnClockSeconds')));here=int(prop('SelectedEra'))==int(prop('EraIndex'));clock='%d:%02d'%(away//60,away%60);clock_next='%d:%02d'%((away+1)//60,(away+1)%60)
    # The state line stands where the manager wrote its CONFIRM line; its other watch texts (task pending, excursion used) have none.
    state=('YOU ARE HERE' if here else ('PINCH SELECT TO TRAVEL' if 'READY' in drawn else 'GO TO THE GATE TO TRAVEL')) if 'CONFIRM TRANSITION' in str(prop('PanelText')) else ''
    readout=all(word not in drawn for word in ['unavailable','locked','seconds away','CONFIRM TRANSITION','ISLANDS']) and state in drawn and (int(prop('EraIndex'))!=1 or ('TIME AWAY FROM HOME - '+clock) in drawn or ('TIME AWAY FROM HOME - '+clock_next) in drawn)
    step={'label':label,'expect':'dial_grab','mode':int(prop('Mode')),'case':S.get('case'),'dial_drag':{'held':held,'from_deg':start,'to_deg':end,'hand_deg':round(angle,1),'era':int(prop('SelectedEra')),'wanted_era':target,'released':not bool(p.get_editor_property('QuestDialHeld')),'plain_dashes':plain,'true_readout':readout,'state':state,'away_seconds':away,'drawn':drawn}}
    H_HAND_STEPS.append(step);h_record()
    if label!='dial_grab' or not held or int(prop('SelectedEra'))!=target or abs(angle-end)>6 or bool(p.get_editor_property('QuestDialHeld')) or not plain or not readout:raise AssertionError('Watch dial drag failed: %r'%step)
    return label
def h_ahead(distance=45.0):
    camera=h_pawn().get_component_by_class(unreal.CameraComponent)
    return camera.get_world_location()+camera.get_forward_vector()*distance
def h_button(name):return h_pawn().get_editor_property(name).get_world_location()
def h_panel():h_pawn().call_method('QuestPanelFrame');h_pawn().call_method('QuestHudFrame')
def h_record():REPORT['hands_only_steps']=H_HAND_STEPS;REPORT['direct_manager_actions']=H_DIRECT;REPORT['hands_only_step_count']=len(H_HAND_STEPS)
def h_pinch(point,right,expect):
    # right is the role: True the main hand, False the off hand. In the one-hand run only the main hand (the left) exists.
    if H_ONE:
        if not right:raise AssertionError('The one-hand run asked for an off-hand pinch: '+str(expect))
        right=False
    h_point(point,right,False);h_frame();h_point(point,right,True);h_frame()
    label=str(h_pawn().get_editor_property('QuestLastHandAction'))
    h_point(point,right,False);h_frame(.4)
    H_HAND_STEPS.append({'label':label,'expect':expect,'mode':int(prop('Mode')),'case':S.get('case')});h_record()
    if label!=expect:raise AssertionError('Hands-only step %s produced %r in mode %d'%(expect,label,int(prop('Mode'))))
    return label
def h_wrist():
    # The watch on the wrist (16 November 2026, night). The off hand is raised as one reads a watch (h_sim.watch_pose: back
    # of the hand to the eye, little-finger side up). Before the watch is calibrated nothing is drawn there and the Watch
    # button opens the (locked) watch; once calibrated the pawn draws the watch on that wrist, facing the eye with twelve
    # o'clock up, and a main-hand pinch on it opens the watch.
    p=h_pawn();joints=h_sim.place_watch(p,False);h_frame();p.call_method('QuestHandDraw');p.call_method('QuestWristFrame',args=(1.0/72.0,))
    shown=bool(p.get_editor_property('QuestWristShown'));calibrated=bool(prop('WatchCalibrated'))
    if shown!=calibrated:raise AssertionError('Wrist watch shown=%r with WatchCalibrated=%r'%(shown,calibrated))
    if not calibrated:
        H_HAND_STEPS.append({'label':'wrist_hidden','expect':'wrist_hidden','mode':int(prop('Mode')),'case':S.get('case')});h_record()
        return h_pinch(h_button('QuestBtnWatch'),True,'open_watch')
    camera=p.get_component_by_class(unreal.CameraComponent);root=p.get_editor_property('QuestWristRoot');dial=p.get_editor_property('QuestWristDial')
    at=dial.get_world_location();eye=camera.get_world_location();to_eye=eye-at;reach=to_eye.length();to_eye=to_eye/reach
    facing=-root.get_up_vector().dot(to_eye);twelve=root.get_forward_vector().dot(camera.get_up_vector());from_wrist=(at-unreal.Vector(*joints['Wrist'])).length()
    era=int(prop('EraIndex'));hand_yaw=p.get_editor_property('QuestWristPivot').get_editor_property('relative_rotation').yaw
    # The small hand leans to the viewer's left (the past mark) in the past and to the right in the present.
    tip=p.get_editor_property('QuestWristHand').get_world_location()-p.get_editor_property('QuestWristPivot').get_world_location();lean=tip.dot(camera.get_right_vector())
    wrist={'shown':shown,'facing_eye':round(facing,3),'twelve_up':round(twelve,3),'cm_from_wrist_keypoint':round(from_wrist,1),'cm_from_eye':round(reach,1),'era':era,'hand_yaw':round(hand_yaw,1),'hand_leans_right_cm':round(lean,2),'visible':bool(dial.is_visible())}
    if facing<0.85 or twelve<0.75 or from_wrist>7.0 or not dial.is_visible() or abs(hand_yaw-(50.0 if era==1 else -50.0))>1.0 or (lean<0)!=(era==1):raise AssertionError('Wrist watch is not where a watch is worn: %r'%wrist)
    # The pinch is heard: the pawn asks the manager's action-sound actor for its watch tick on the frame after the action.
    sfx=[a for a in unreal.GameplayStatics.get_all_actors_of_class(p,unreal.Actor) if 'ReleaseActionSfx' in a.get_class().get_name()]
    def h_sound():return {'pawn_ticks':int(p.get_editor_property('QuestTicks')),'sfx_actors':len(sfx),'cues_played':int(sfx[0].get_editor_property('CuePlayCount')) if sfx else None,'cues_suppressed':int(sfx[0].get_editor_property('CueSuppressedCount')) if sfx else None}
    before=h_sound()
    label=h_pinch(at+to_eye*1.2,True,'open_watch_wrist');after=h_sound();wrist['sound_before']=before;wrist['sound_after']=after;H_HAND_STEPS[-1]['wrist']=wrist;h_record()
    if int(prop('Mode'))!=4:raise AssertionError('The wrist watch did not open the watch: mode %d'%int(prop('Mode')))
    if after['pawn_ticks']<=before['pawn_ticks']:raise AssertionError('The pinch on the wrist watch asked for no tick: %r'%wrist)
    return label
def h_long_left(point):
    h_point(point,False,False);h_frame();h_point(point,False,True);h_frame(.6);h_frame(.6)
    label=str(h_pawn().get_editor_property('QuestLastHandAction'));h_point(point,False,False);h_frame(.4)
    H_HAND_STEPS.append({'label':label,'expect':'gesture_pause','mode':int(prop('Mode')),'case':S.get('case')});h_record()
    if label!='gesture_pause':raise AssertionError('Pause gesture produced %r'%label)
    return label
def action(name,*args):
    mode=int(prop('Mode'));menu=bool(prop('ReleaseMenuActive'))
    if H_ONE:
        # One hand: the Back button closes and skips the recollections, the HUD Menu button pauses.
        if name=='CloseModal' and mode in (1,4,5,6):h_panel();return h_pinch(h_button('QuestBtnBack'),True,{1:'close_photo',4:'close_watch',5:'close_journal',6:'pause_resume'}[mode])
        if name=='OpenPause' and mode==0 and not menu:h_panel();return h_pinch(h_button('QuestBtnMenu'),True,'open_pause')
        if name=='SkipRecollections' and mode==3 and bool(prop('IntroActive')):h_panel();return h_pinch(h_button('QuestBtnBack'),True,'skip_recollections')
    if name=='Interact' and mode==0 and not menu:return h_pinch(h_ahead(),True,'interact')
    if name=='AdvanceDialogue' and mode==3 and not bool(prop('DialogueWaitingChoice')):return h_pinch(h_ahead(),True,'advance_dialogue')
    if name=='ChooseDialogue' and mode==3 and bool(prop('DialogueWaitingChoice')):
        h_panel();return h_pinch(h_button('QuestChoice%d'%int(args[0])),True,'choose_%d'%int(args[0]))
    if name=='SkipRecollections' and mode==3 and bool(prop('IntroActive')):return h_pinch(h_ahead(),False,'skip_recollections')
    if name=='FlipPhoto' and mode==1:return h_pinch(h_ahead(),True,'flip_photo')
    if name=='CloseModal' and mode in (1,4,5):return h_pinch(h_ahead(),False,{1:'close_photo',4:'close_watch',5:'close_journal'}[mode])
    if name=='CloseModal' and mode==6:return h_pinch(h_ahead(),False,'pause_resume')
    if name=='CloseDocument' and mode==2:return h_pinch(h_ahead(),True,'close_document')
    if name=='OpenPause' and mode==0 and not menu:return h_long_left(h_ahead())
    if name=='OpenWatch' and mode==0 and not menu:
        h_panel()
        if H_ONE:return h_pinch(h_button('QuestBtnWatch'),True,'open_watch')
        return h_wrist()
    if name=='OpenJournal' and mode==0 and not menu:h_panel();return h_pinch(h_button('QuestBtnJournal'),True,'open_journal')
    if name=='RotateDial' and mode==4:
        h_panel()
        if bool(h_pawn().get_editor_property('QuestDialVisible')):return h_dial(int(args[0]))
        down=int(args[0])>0;return h_pinch(h_button('QuestBtnDown' if down else 'QuestBtnUp'),True,'dial_right' if down else 'dial_left')
    if name=='ConfirmWatch' and mode==4:h_panel();return h_pinch(h_button('QuestBtnOk'),True,'confirm_watch')
    if name=='TurnJournal' and mode==5:
        h_panel();down=int(args[0])>0;return h_pinch(h_button('QuestBtnDown' if down else 'QuestBtnUp'),True,'journal_next' if down else 'journal_previous')
    if name in ('HandleOne','HandleTwo','HandleThree') and mode==6:
        i={'HandleOne':1,'HandleTwo':2,'HandleThree':3}[name];h_panel();return h_pinch(h_button('QuestChoice%d'%i),True,'pause_row_%d'%i)
    if name=='ReleaseSelect' and menu:
        index=int(args[0]);h_panel()
        for _ in range(12):
            current=int(prop('ReleaseMenuSelection'))
            if current==index:break
            down=index>current;h_pinch(h_button('QuestBtnDown' if down else 'QuestBtnUp'),True,'menu_down' if down else 'menu_up')
        if int(prop('ReleaseMenuSelection'))!=index:raise AssertionError('Menu selection could not reach row %d by pinch'%index)
        if len(args)>1 and args[1]:return h_pinch(h_button('QuestBtnOk'),True,'menu_select')
        return None
    H_DIRECT.append({'action':name,'args':[str(a) for a in args],'mode':mode,'menu':menu,'case':S.get('case')});h_record()
    return S['manager'].call_method(name,args=tuple(args))'''
h_replace("def action(name,*args):return S['manager'].call_method(name,args=tuple(args))", H_ACTION)
h_replace("REPORT['xr_pawn_fixture']={", """REPORT['hands_only_fixture']={'simulated_fingertips':True,'hand_tracking_hardware_tested':False,'controller_keys_injected':0,'pinch':'thumb-index distance (2.5 cm on, 4.5 cm off) on the pawn members QuestSimLeft/Right Thumb and Index','ray':'eye-to-pinch-point ray from the HMD-locked camera','player_action_primitive':'every intercepted manager action is a pinch on the pawn; direct calls are listed in direct_manager_actions'}
REPORT['xr_pawn_fixture']={""")
H_ONE_RUN = unreal.SystemLibrary.parse_param(unreal.SystemLibrary.get_command_line(), 'Quest3OneHandLeftQA')
for old, new in [('quest3_xr_story_runtime_validation.json', 'quest3_onehand_left_story_runtime_validation.json' if H_ONE_RUN else 'quest3_hands_story_runtime_validation.json'),
                 ("'quest3_xr_story'", "'quest3_onehand_left_story'" if H_ONE_RUN else "'quest3_hands_story'"), ('YQ3XRQA_', 'YQ3OHQA_' if H_ONE_RUN else 'YQ3HSQA_')]:
    if old not in source:
        raise RuntimeError('Runtime output label changed: ' + old)
    source = source.replace(old, new)
import ast as h_ast
h_ast.parse(source)
exec(compile(source, str(H_ROOT / 'Python/validate_brief_m2.py'), 'exec'), globals())
