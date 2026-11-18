"""Author Milestone A as native runtime Blueprints; Python is build tooling only.

All new story copy is provisional. No template character/controller graph is
replaced. Save writes are synchronous and only contain committed story flags.
"""
from pathlib import Path
import json, sys, textwrap, traceback
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import opening_graph as og

PATH='/Game/Opening/Blueprints/BP_OpeningActions'
CLASS=PATH+'.BP_OpeningActions_C'
SAVE_PATH='/Game/Opening/Blueprints/BP_OpeningSave'
SAVE_CLASS=SAVE_PATH+'.BP_OpeningSave_C'
MATH='/Script/Engine.KismetMathLibrary.'
SYS='/Script/Engine.KismetSystemLibrary.'
GS='/Script/Engine.GameplayStatics.'
ACT='/Script/Engine.Actor.'
PC='/Script/Engine.PlayerController.'
CTL='/Script/Engine.Controller.'
CAM='/Script/Engine.PlayerCameraManager.'
CHAR='/Script/Engine.Character.'
FLAGS=['HomeExplored','PhotoSeen','PhotoBackSeen','LetterRead','MotherMet','MotherSpoken','MotherPromise','RepairIdentified','ComponentCollected','ComponentPlaced','WatchCalibrated','AnchorActivated','DrawerOpen']
REFS=['PhotoActor','LetterActor','MotherActor','BenchActor','ComponentActor','DrawerActor','AnchorActor']
MATH_LITERALS=[]
FUNCTIONS={'Initialize':{},'LoadProgress':{},'SaveProgress':{},'_SaveCopy':{},'ApplyState':{},'RefreshUI':{},'UpdateTarget':{},'Interact':{},'InspectSelected':{},'CloseModal':{},'OpenPause':{},'OpenWatch':{},'OpenJournal':{},'FlipPhoto':{},'MotherTopic':{},'MotherOfferHelp':{},'OpenMother':{},'OpenLetter':{},'OpenPhoto':{},'UseWorkbench':{},'ToggleDrawer':{},'PickupComponent':{},'ActivateAnchor':{},'ConfirmWatch':{},'HandleOne':{},'HandleTwo':{},'HandleThree':{},'InputFrame':{},'UpdateStep':{'DeltaSeconds':'real'},'SetMode':{'NewMode':'int'},'RestorePhoto':{}}

def wrap(value,width=67):return '\n'.join(textwrap.fill(line,width=width) if line else '' for line in value.split('\n'))
def vpin(value):return isinstance(value,unreal.BlueprintGraphPin)
class Flow:
 def __init__(self,g,exec_pin=None):self.g=g;self.cur=exec_pin if exec_pin is not None else g.entry
 def call(self,path,/,**params):
  n=self.g.call(path)
  for k,v in params.items():
   if vpin(v):og.link(v,og.pin_in(n,k))
   else:
    og.default(n,k,v)
    if path.startswith(MATH):MATH_LITERALS.append((n,k,v))
  has_exec=any(str(og.P.get_pin_name(p))=='execute' for p in og.L.list_input_pins(n))
  if has_exec:
   ep=og.pin_in(n)
   og.link(self.cur,ep);tp=og.L.find_then_pin(n)
   if og.P.is_valid(tp):self.cur=tp
  return n
 def data(self,path,out='ReturnValue',/,**params):return og.value_pin(self.call(path,**params),out)
 def var(self,name,owner=None,cls=''):return og.value_pin(self.g.get(name,owner=owner,class_path=cls),name)
 def set(self,name,value,owner=None,cls=''):
  n=self.g.set(name,value,owner=owner,class_path=cls);og.link(self.cur,og.pin_in(n));self.cur=og.pin_out(n);return self
 def own(self,name,**params):return self.call(CLASS+':'+name,**params)
 def branch(self,condition):
  n=self.g.branch(condition);og.link(self.cur,og.pin_in(n));return Flow(self.g,og.pin_out(n,'then')),Flow(self.g,og.pin_out(n,'else'))
 def eq(self,a,b):return self.data(MATH+'EqualEqual_IntInt',A=a,B=b)
 def not_(self,a):return self.data(MATH+'Not_PreBool',A=a)
 def and_(self,a,b):return self.data(MATH+'BooleanAND',A=a,B=b)
 def or_(self,a,b):return self.data(MATH+'BooleanOR',A=a,B=b)
 def valid(self,a):return self.data(SYS+'IsValid',Object=a)
 def tag(self,a,tag):return self.data(ACT+'ActorHasTag',**{'self':a,'Tag':tag})
 def key(self,key,held=False):return self.data(PC+('IsInputKeyDown' if held else 'WasInputKeyJustPressed'),**{'self':self.var('Controller'),'Key':key})
 def notice(self,text):self.set('Notice',wrap(text));self.set('NoticeRemaining',4.5);return self
 def panel(self,mode,title,body,footer):
  self.set('PanelTitle',title);self.set('PanelText',wrap(body,38 if mode==1 else 67));self.set('PanelFooter',footer);self.own('SetMode',NewMode=mode);return self
 def commit(self):self.own('SaveProgress');self.own('RefreshUI');return self
 def guarded_mode(self,mode):return self.branch(self.eq(self.var('Mode'),mode))

def build_actions():
 save=og.blueprint(SAVE_PATH,unreal.SaveGame)
 for name in FLAGS:og.member(save,name,'bool',False)
 og.member(save,'Chapter','int',1);og.member(save,'Era','string','Present');og.member(save,'SafeLocationId','string','home.porch')
 og.member(save,'SchemaVersion','int',1)
 og.compile_bp(save,save=True)
 bp=og.blueprint(PATH,unreal.Actor)
 MATH_LITERALS.clear()
 old_events=og.events(bp);old_events.editor.remove_nodes(old_events.editor.list_all_nodes())
 for name in FLAGS+['PhotoBack','Testing']:og.member(bp,name,'bool',False)
 for name in ['Prompt','PanelTitle','PanelText','PanelFooter','Objective','Notice']:og.member(bp,name,'string','')
 og.member(bp,'Mode','int',0);og.member(bp,'NoticeRemaining','real',0);og.member(bp,'TestElapsed','real',0);og.member(bp,'SaveSucceeded','bool',False)
 og.member(bp,'CalibrationSeconds','real',1.5,instance_editable=True)
 og.member(bp,'InteractionRange','real',260,instance_editable=True)
 og.member(bp,'SaveSlot','string','Yesterday_Opening_v1',instance_editable=True)
 for name in REFS:og.member(bp,name,og.object_type(unreal.Actor),instance_editable=True)
 for name,cls in [('Player',unreal.Character),('Controller',unreal.PlayerController),('Camera',unreal.PlayerCameraManager),('Target',unreal.Actor),('HeldPhoto',unreal.Actor)]:og.member(bp,name,og.object_type(cls))
 og.member(bp,'SaveRef',og.object_type(save))
 og.member(bp,'InspectionMaterial',og.object_type(unreal.MaterialInterface),instance_editable=True);og.member(bp,'PhotoOriginalMaterial',og.object_type(unreal.MaterialInterface))
 og.member(bp,'DebugTraceStart',og.struct_type('vector'));og.member(bp,'DebugTraceEnd',og.struct_type('vector'));og.member(bp,'DebugTraceHit','bool',False);og.member(bp,'DebugHitActor',og.object_type(unreal.Actor));og.member(bp,'DebugHasTag','bool',False);og.member(bp,'DebugDistance','real',0)
 og.member(bp,'IgnoredActors',og.array_type(og.object_type(unreal.Actor)))
 og.member(bp,'PhotoReturn',og.struct_type('transform'))
 og.member(bp,'DrawerReturn',og.struct_type('rotator'))
 # Only rebuild this new manager's own functions; preserve scene actor references.
 for n,params in FUNCTIONS.items():
  old=og.L.find_graph(bp,n)
  if old:
   ed=og.E.get_graph_editor(old);ed.remove_nodes([node for node in ed.list_all_nodes() if node.get_class().get_name() not in ['K2Node_FunctionEntry','K2Node_FunctionResult']])
  og.function(bp,n,inputs=params,reset=False)
 og.compile_bp(bp)
 hud_stub=og.blueprint('/Game/Opening/Blueprints/BP_OpeningHUD',unreal.HUD);og.compile_bp(hud_stub,save=True)
 def fn(n):return Flow(og.function(bp,n,reset=False))
 def statecopy(f,to_save):
  for flag in FLAGS:
   if to_save:f.set(flag,f.var(flag),f.var('SaveRef'),SAVE_CLASS)
   else:f.set(flag,f.var(flag,f.var('SaveRef'),SAVE_CLASS))
 def hidden(f,ref,value):
  f.call(ACT+'SetActorHiddenInGame',**{'self':f.var(ref),'bNewHidden':value})
  f.call(ACT+'SetActorEnableCollision',**{'self':f.var(ref),'bNewActorEnableCollision':f.not_(value) if vpin(value) else not value})
  comp=f.data(ACT+'GetComponentByClass',**{'self':f.var(ref),'ComponentClass':'/Script/Engine.StaticMeshComponent'})
  off,on=f.branch(value)
  off.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled',**{'self':comp,'NewType':'NoCollision'})
  on.call('/Script/Engine.PrimitiveComponent.SetCollisionEnabled',**{'self':comp,'NewType':'QueryOnly'})
  join=f.g.set('Prompt','');og.link(off.cur,og.pin_in(join));og.link(on.cur,og.pin_in(join));f.cur=og.pin_out(join)
 def modalclose(f):f.own('CloseModal')

 # Initialization is a thin layer on the existing native template characters.
 f=fn('Initialize')
 f.set('Player',f.data(GS+'GetPlayerCharacter',PlayerIndex=0));f.set('Controller',f.data(GS+'GetPlayerController',PlayerIndex=0));f.set('Camera',f.data(GS+'GetPlayerCameraManager',PlayerIndex=0))
 f,not_ready=f.branch(f.and_(f.valid(f.var('Player')),f.valid(f.var('Controller'))))
 f.call(ACT+'SetTickableWhenPaused',**{'self':f.var('Controller'),'bTickableWhenPaused':True})
 f.set('bShouldPerformFullTickWhenPaused',True,f.var('Controller'),'/Script/Engine.PlayerController')
 f.call(SYS+'ExecuteConsoleCommand',Command='DisableAllScreenMessages',SpecificPlayer=f.var('Controller'))
 arr=f.g.call('/Script/Engine.KismetArrayLibrary.Array_Add');og.link(f.var('IgnoredActors'),og.pin_in(arr,'TargetArray'));og.link(f.var('Player'),og.pin_in(arr,'NewItem'));og.link(f.cur,og.pin_in(arr));f.cur=og.pin_out(arr)
 f.set('DrawerReturn',f.data(ACT+'K2_GetActorRotation',**{'self':f.var('DrawerActor')}))
 f.call(PC+'ClientSetHUD',**{'self':f.var('Controller'),'NewHUDClass':'/Game/Opening/Blueprints/BP_OpeningHUD.BP_OpeningHUD_C'})
 f.own('LoadProgress');f.own('RefreshUI')

 f=fn('SetMode');mode=f.g.input('NewMode');f.set('Mode',mode)
 f.call(CTL+'ResetIgnoreMoveInput',**{'self':f.var('Controller')});f.call(CTL+'ResetIgnoreLookInput',**{'self':f.var('Controller')})
 yes,no=f.branch(f.not_(f.eq(mode,0)))
 yes.call(CTL+'SetIgnoreMoveInput',**{'self':yes.var('Controller'),'bNewMoveInput':True});yes.call(CTL+'SetIgnoreLookInput',**{'self':yes.var('Controller'),'bNewLookInput':True})

 f=fn('SaveProgress');exists,missing=f.branch(f.valid(f.var('SaveRef')))
 created=missing.call(GS+'CreateSaveGameObject',SaveGameClass=SAVE_CLASS);missing.set('SaveRef',og.value_pin(created))
 # Merge both exec paths once the authoritative save object exists.
 copy=og.function(bp,'_SaveCopy',reset=False);cf=Flow(copy);statecopy(cf,True)
 cf.set('Chapter',1,cf.var('SaveRef'),SAVE_CLASS);cf.set('Era','Present',cf.var('SaveRef'),SAVE_CLASS);cf.set('SafeLocationId','home.porch',cf.var('SaveRef'),SAVE_CLASS)
 result=cf.call(GS+'SaveGameToSlot',SaveGameObject=cf.var('SaveRef'),SlotName=cf.var('SaveSlot'),UserIndex=0)
 cf.set('SaveSucceeded',og.value_pin(result))
 ok,bad=cf.branch(og.value_pin(result));bad.notice('Progress remains in this session, but the save could not be written.')
 og.compile_bp(bp)
 exists.own('_SaveCopy');missing.own('_SaveCopy')

 f=fn('LoadProgress');f.own('RestorePhoto');f.set('Testing',False);f.set('TestElapsed',0)
 f.call(GS+'SetGamePaused',bPaused=False);f.own('SetMode',NewMode=0)
 has,none=f.branch(f.data(GS+'DoesSaveGameExist',SlotName=f.var('SaveSlot'),UserIndex=0))
 loaded=has.call(GS+'LoadGameFromSlot',SlotName=has.var('SaveSlot'),UserIndex=0)
 cast=has.g.cast(SAVE_CLASS,og.value_pin(loaded));og.link(has.cur,og.pin_in(cast));has.cur=og.pin_out(cast)
 has.set('SaveRef',has.g.cast_value(cast));statecopy(has,False);has.own('ApplyState');has.own('RefreshUI');has.notice('Progress restored. You are at the safe porch entrance.')
 has.call(ACT+'K2_SetActorLocation',**{'self':has.var('Player'),'NewLocation':unreal.Vector(120,1240,991),'bSweep':False,'bTeleport':True})
 failed=Flow(has.g,og.pin_out(cast,'CastFailed'));failed.notice('This save could not be read. Earned progress has not been overwritten.')
 none.call(GS+'CreateSaveGameObject',SaveGameClass=SAVE_CLASS);none.own('ApplyState');none.own('RefreshUI')

 f=fn('ApplyState');visible=f.and_(f.var('DrawerOpen'),f.not_(f.var('ComponentCollected')));hidden(f,'ComponentActor',f.not_(visible))
 yes,no=f.branch(f.var('DrawerOpen'))
 yes.call(ACT+'K2_SetActorRotation',**{'self':yes.var('DrawerActor'),'NewRotation':unreal.Rotator(pitch=-75,yaw=0,roll=0),'bTeleportPhysics':True})
 no.call(ACT+'K2_SetActorRotation',**{'self':no.var('DrawerActor'),'NewRotation':no.var('DrawerReturn'),'bTeleportPhysics':True})

 f=fn('RefreshUI')
 objectives=[('AnchorActivated','First anchor registered. Your calibrated watch is ready.'),('WatchCalibrated','Activate the time anchor on the porch.'),('ComponentPlaced','Test the final Chronowatch calibration at the workbench.'),('ComponentCollected','Fit the alignment collar at the workbench.'),('RepairIdentified','Open the parts box and take the alignment collar.'),('MotherSpoken','Visit your workbench for the final calibration.'),('LetterRead','Speak with Mother in the surviving room.'),('PhotoSeen','Read the letter on the table.')]
 tail=f
 for flag,text in objectives:
  yes,tail=tail.branch(tail.var(flag));yes.set('Objective',text)
 tail.set('Objective','Explore the surviving room and inspect the family photograph.')

 f=fn('UpdateTarget');f.set('Target',None);f.set('Prompt','')
 active,stop=f.guarded_mode(0)
 loc=active.data(CAM+'GetCameraLocation',**{'self':active.var('Camera')});rot=active.data(CAM+'GetCameraRotation',**{'self':active.var('Camera')})
 direction=active.data(MATH+'GetForwardVector',InRot=rot);length=active.data(MATH+'Multiply_VectorFloat',A=direction,B=900)
 end=active.data(MATH+'Add_VectorVector',A=loc,B=length)
 trace=active.call(SYS+'LineTraceSingle',Start=loc,End=end,TraceChannel='TraceTypeQuery1',bTraceComplex=False,ActorsToIgnore=active.var('IgnoredActors'),DrawDebugType='None',bIgnoreSelf=True)
 active.set('DebugTraceStart',loc);active.set('DebugTraceEnd',end);active.set('DebugTraceHit',og.value_pin(trace,'ReturnValue'))
 hit,miss=active.branch(og.value_pin(trace,'ReturnValue'))
 br=hit.call(GS+'BreakHitResult',Hit=og.value_pin(trace,'OutHit'));actor=og.value_pin(br,'HitActor')
 hit.set('DebugHitActor',actor);hit.set('DebugHasTag',hit.tag(actor,'Opening.Interactable'))
 eligible,blocked=hit.branch(hit.tag(actor,'Opening.Interactable'))
 distance=eligible.data(ACT+'GetDistanceTo',**{'self':actor,'OtherActor':eligible.var('Player')})
 eligible.set('DebugDistance',distance)
 near,far=eligible.branch(eligible.data(MATH+'LessEqual_DoubleDouble',A=distance,B=eligible.var('InteractionRange')))
 near.set('Target',actor)
 tail=near
 for tag,prompt in [('home.photo','F / E  Inspect family photograph'),('home.letter','E  Read the letter'),('npc.mother','E  Speak with Mother'),('home.anchor','E  Activate time anchor'),('home.calibration_component','E  Take alignment collar')]:
  yes,tail=tail.branch(tail.tag(actor,tag));yes.set('Prompt',prompt)
 yes,tail=tail.branch(tail.tag(actor,'home.drawer'))
 opened,closed=yes.branch(yes.var('DrawerOpen'));opened.set('Prompt','E  Close parts box');closed.set('Prompt','E  Open parts box')
 bench,tail=tail.branch(tail.tag(actor,'home.workbench'))
 staged=bench
 for flag,prompt in [('WatchCalibrated','E  Examine calibrated Chronowatch'),('ComponentPlaced','E  Test final calibration'),('ComponentCollected','E  Fit alignment collar'),('RepairIdentified','E  Check missing alignment collar')]:
  yes,staged=staged.branch(staged.var(flag));yes.set('Prompt',prompt)
 staged.set('Prompt','E  Examine the final calibration')

 f=fn('Interact');f.own('UpdateTarget');yes,none=f.branch(f.valid(f.var('Target')));tail=yes
 for tag,action in [('home.photo','OpenPhoto'),('home.letter','OpenLetter'),('npc.mother','OpenMother'),('home.workbench','UseWorkbench'),('home.drawer','ToggleDrawer'),('home.calibration_component','PickupComponent'),('home.anchor','ActivateAnchor')]:
  yes,tail=tail.branch(tail.tag(tail.var('Target'),tag));yes.own(action)
 f=fn('InspectSelected');f.own('UpdateTarget');yes,no=f.branch(f.valid(f.var('Target')))
 photo,rest=yes.branch(yes.tag(yes.var('Target'),'home.photo'));photo.own('OpenPhoto')
 letter,rest=rest.branch(rest.tag(rest.var('Target'),'home.letter'));letter.own('OpenLetter')
 rest.notice('This object has no separate inspection view.')

 f=fn('OpenPhoto');f.set('HomeExplored',True);f.set('PhotoSeen',True);f.set('PhotoBack',False)
 f.set('HeldPhoto',f.var('PhotoActor'));f.set('PhotoReturn',f.data(ACT+'GetTransform',**{'self':f.var('HeldPhoto')}))
 photo_mesh=f.data(ACT+'GetComponentByClass',**{'self':f.var('HeldPhoto'),'ComponentClass':'/Script/Engine.StaticMeshComponent'})
 f.set('PhotoOriginalMaterial',f.data('/Script/Engine.PrimitiveComponent.GetMaterial',**{'self':photo_mesh,'ElementIndex':0}))
 f.call('/Script/Engine.PrimitiveComponent.SetMaterial',**{'self':photo_mesh,'ElementIndex':0,'Material':f.var('InspectionMaterial')})
 f.call(ACT+'SetActorEnableCollision',**{'self':f.var('HeldPhoto'),'bNewActorEnableCollision':False})
 camloc=f.data(CAM+'GetCameraLocation',**{'self':f.var('Camera')});camrot=f.data(CAM+'GetCameraRotation',**{'self':f.var('Camera')})
 fw=f.data(MATH+'GetForwardVector',InRot=camrot);rr=f.data(MATH+'GetRightVector',InRot=camrot)
 ahead=f.data(MATH+'Multiply_VectorFloat',A=fw,B=75);side=f.data(MATH+'Multiply_VectorFloat',A=rr,B=-23)
 position=f.data(MATH+'Add_VectorVector',A=f.data(MATH+'Add_VectorVector',A=camloc,B=ahead),B=side)
 f.call(ACT+'K2_SetActorLocation',**{'self':f.var('HeldPhoto'),'NewLocation':position,'bSweep':False,'bTeleport':True})
 look=f.data(MATH+'FindLookAtRotation',Start=position,Target=camloc)
 f.call(ACT+'K2_SetActorRotation',**{'self':f.var('HeldPhoto'),'NewRotation':look,'bTeleportPhysics':True})
 f.panel(1,'Family photograph','A family photograph, kept in the surviving room.\n\nFor a moment, hold it still. The reverse has a handwritten note.', 'R  Turn over    Left / Right  Rotate\nE or F  Put back    Esc  Pause')
 f.commit()
 f=fn('FlipPhoto');active,no=f.guarded_mode(1);active.set('PhotoBack',active.not_(active.var('PhotoBack')))
 active.call(ACT+'K2_AddActorLocalRotation',**{'self':active.var('HeldPhoto'),'DeltaRotation':unreal.Rotator(pitch=0,yaw=180,roll=0),'bSweep':False,'bTeleport':True})
 back,front=active.branch(active.var('PhotoBack'));back.set('PhotoBackSeen',True);back.set('PanelText',wrap('On the reverse, in familiar handwriting:\n\n"Home. Keep this close."\n\nYou have found a personal family keepsake.',38));back.commit()
 front.set('PanelText',wrap('The photograph shows the family together. Its worn frame has been repaired rather than replaced.\n\nR  Turn over to read the reverse.',38))
 f=fn('RestorePhoto');yes,no=f.branch(f.valid(f.var('HeldPhoto')))
 photo_mesh=yes.data(ACT+'GetComponentByClass',**{'self':yes.var('HeldPhoto'),'ComponentClass':'/Script/Engine.StaticMeshComponent'})
 yes.call('/Script/Engine.PrimitiveComponent.SetMaterial',**{'self':photo_mesh,'ElementIndex':0,'Material':yes.var('PhotoOriginalMaterial')})
 yes.call(ACT+'K2_SetActorTransform',**{'self':yes.var('HeldPhoto'),'NewTransform':yes.var('PhotoReturn'),'bSweep':False,'bTeleport':True})
 yes.call(ACT+'SetActorEnableCollision',**{'self':yes.var('HeldPhoto'),'bNewActorEnableCollision':True});yes.set('HeldPhoto',None)
 f=fn('OpenLetter');f.set('HomeExplored',True);f.set('LetterRead',True)
 f.panel(2,'A letter from Mother','"You have worked on that watch for nearly five years. Finish its last adjustment carefully, and come and talk to me before you set out.\n\nThere is no need to rush the part that matters.\n\nLove, Mother"','E / F  Close    Esc  Pause');f.commit()
 f=fn('OpenMother');f.set('HomeExplored',True);f.set('MotherMet',True)
 ready,early=f.branch(f.and_(f.var('PhotoSeen'),f.var('LetterRead')))
 ready.panel(3,'Mother','Mother: "You found them. I wanted you to have a quiet moment before the last test. How is the watch?"\n\n1  Ask about the final calibration\n2  Offer to help before leaving\n3  Say goodbye','1 / 2 / 3  Choose    E  End conversation')
 early.panel(3,'Mother','Mother: "Take a moment in the surviving room. The photograph and my letter are on the table. I will be here."\n\n1  Listen\n2  Offer to help\n3  Leave for now','1 / 2 / 3  Choose    E  End conversation');ready.commit();early.commit()
 f=fn('MotherTopic');f.own('RefreshUI');ready,early=f.branch(f.and_(f.var('PhotoSeen'),f.var('LetterRead')))
 ready.set('MotherSpoken',True);ready.set('PanelText',wrap('Mother: "Nearly five years of patient work. This is the last alignment, not the beginning. The spare collar is in the parts box by your bench. Fit it, then test the watch.\n\n1  Listen again\n2  Offer to help before leaving\n3  Say goodbye'));ready.commit()
 early.set('PanelText',wrap('Mother: "Take your time with the photograph and letter. We can talk about your work when you are ready.\n\n3  Leave for now'))
 f=fn('MotherOfferHelp');f.set('MotherPromise',True);f.set('PanelText',wrap('Mother: "Thank you. First, finish the calibration carefully. We can decide what needs doing after that."\n\n1  Ask about the final calibration\n3  Say goodbye'));f.commit()

 f=fn('UseWorkbench');ready,no=f.branch(f.var('MotherSpoken'));no.notice('Speak with Mother after looking at the photograph and letter.')
 calibrated,rest=ready.branch(ready.var('WatchCalibrated'));calibrated.own('OpenWatch')
 placed,rest=rest.branch(rest.var('ComponentPlaced'));placed.set('Testing',True);placed.set('TestElapsed',0);placed.panel(4,'Final Chronowatch calibration','The repaired assembly is steady. Testing the final alignment...\n\nClosing the watch or opening the pause menu cancels this test safely. The fitted collar stays in place.','Q / E  Cancel test    Esc  Pause')
 collected,rest=rest.branch(rest.var('ComponentCollected'));collected.set('ComponentPlaced',True);collected.panel(2,'Alignment collar fitted','You carefully fit the spare alignment collar. The last adjustment is in place.\n\nReturn to the workbench and test the device.','E  Close    Esc  Pause');collected.commit()
 identified,rest=rest.branch(rest.var('RepairIdentified'));identified.notice('The alignment collar is missing. Check the parts box beside the workbench.')
 rest.set('RepairIdentified',True);rest.panel(2,'The last calibration','Five years of repaired parts are already assembled here. One alignment collar is missing from its seat.\n\nThe spare collar is in the parts box beside the bench. Take it, fit it, and run the last test.','E  Close    Esc  Pause');rest.commit()
 f=fn('ToggleDrawer');f.set('DrawerOpen',f.not_(f.var('DrawerOpen')));f.own('ApplyState');f.commit()
 f=fn('PickupComponent');allowed,no=f.branch(f.and_(f.var('RepairIdentified'),f.and_(f.var('DrawerOpen'),f.not_(f.var('ComponentCollected')))))
 allowed.set('ComponentCollected',True);allowed.own('ApplyState');allowed.notice('Alignment collar added to quest items. Return it to the workbench.');allowed.commit()
 no.notice('Check the workbench first. Important parts stay in their designated tray.')
 f=fn('ActivateAnchor');ready,no=f.branch(f.var('WatchCalibrated'));no.notice('The Chronowatch needs its final calibration before it can register this anchor.')
 ready.set('AnchorActivated',True);ready.notice('First time anchor registered. Calibration complete.');ready.commit()

 f=fn('OpenWatch');f.own('RestorePhoto');ready,no=f.branch(f.var('WatchCalibrated'))
 ready.panel(4,'Chronowatch','A handmade device, assembled from repaired parts.\n\nPresent era: Verdant\nAnchor: home porch\n\nThe dial selects a destination; confirmation is separate. No other anchor is registered yet.\n\nFour island controls: Verdant / locked / locked / locked\nTime pause: not unlocked\nPerspective: no eligible event discovered','Q  Close    E  Confirm at nearby anchor    Esc  Pause')
 no.panel(4,'Chronowatch','The final alignment is unfinished.\n\nSpeak with Mother, examine the workbench, find the spare collar, fit it, and test the device.\n\nThe dial and island controls remain locked until calibration.','Q  Close    Esc  Pause')
 f=fn('ConfirmWatch');ready,no=f.branch(f.var('WatchCalibrated'));distance=ready.data(ACT+'GetDistanceTo',**{'self':ready.var('Player'),'OtherActor':ready.var('AnchorActor')})
 near,far=ready.branch(ready.data(MATH+'LessEqual_DoubleDouble',A=distance,B=260))
 clear,blocked=near.branch(near.data(CTL+'LineOfSightTo',**{'self':near.var('Controller'),'Other':near.var('AnchorActor'),'bAlternateChecks':False}));clear.own('ActivateAnchor');blocked.notice('You need a clear view of the porch anchor.')
 far.notice('Travel and anchor registration require the designated porch anchor.')
 no.notice('Finish calibration at the workbench first.')
 f=fn('OpenJournal');f.own('RestorePhoto');f.set('PanelText','CURRENT OBJECTIVE\n');f.set('PanelTitle','Journal')
 def append(flow,text):flow.set('PanelText',flow.data('/Script/Engine.KismetStringLibrary.Concat_StrStr',A=flow.var('PanelText'),B='\n'+wrap(text)))
 append(f,f.var('Objective')) if False else None
 f.set('PanelText',f.data('/Script/Engine.KismetStringLibrary.Concat_StrStr',A='CURRENT OBJECTIVE\n',B=f.var('Objective')))
 current=f
 for flag,text in [('PhotoSeen','CLUE — The family photograph is kept in the surviving room.'),('PhotoBackSeen','CLUE — The reverse reads: "Home. Keep this close."'),('LetterRead','DOCUMENT — Mother asks you to finish the last adjustment carefully.'),('MotherMet','PERSON — Mother, at home.'),('MotherSpoken','KNOWLEDGE — You have worked on the watch for nearly five years.'),('MotherPromise','COMMITMENT — You offered to help before leaving.'),('ComponentCollected','QUEST ITEM — Alignment collar, held safely or fitted to the watch.'),('WatchCalibrated','WATCH — Final calibration complete.'),('AnchorActivated','LOCATION — Home porch anchor discovered and registered.')]:
  yes,no=current.branch(current.var(flag));append(yes,text)
  # Join each optional note into a dedicated no-op variable set.
  join=current.g.set('PanelTitle','Journal');og.link(yes.cur,og.pin_in(join));og.link(no.cur,og.pin_in(join));current=Flow(current.g,og.pin_out(join))
 current.set('PanelFooter','Tab / E  Close    Esc  Pause');current.own('SetMode',NewMode=5)
 f=fn('CloseModal');f.own('RestorePhoto');f.set('Testing',False);f.set('TestElapsed',0);f.call(GS+'SetGamePaused',bPaused=False);f.own('SetMode',NewMode=0);f.own('RefreshUI')
 f=fn('OpenPause');f.own('RestorePhoto');f.set('Testing',False);f.panel(6,'Paused','1  Resume\n\n2  Save committed progress\n\n3  Load last saved progress\n\nLoading returns you to the safe porch entrance. Inspection and unfinished tests close safely.','Esc / 1  Resume    2  Save    3  Load');f.call(GS+'SetGamePaused',bPaused=True)

 f=fn('HandleOne');dialogue,other=f.guarded_mode(3);dialogue.own('MotherTopic');pause,other=other.guarded_mode(6);pause.own('CloseModal')
 f=fn('HandleTwo');dialogue,other=f.guarded_mode(3);dialogue.own('MotherOfferHelp');pause,other=other.guarded_mode(6);pause.own('SaveProgress');success,failure=pause.branch(pause.var('SaveSucceeded'));success.notice('Committed progress saved.')
 f=fn('HandleThree');dialogue,other=f.guarded_mode(3);dialogue.own('CloseModal');pause,other=other.guarded_mode(6);pause.own('LoadProgress')
 f=fn('InputFrame')
 # Each accepted key takes one branch; menu/dialogue/watch never fall through.
 pause,normal=f.guarded_mode(6)
 for key,action in [('Escape','CloseModal'),('One','HandleOne'),('Two','HandleTwo'),('Three','HandleThree')]:yes,pause=pause.branch(pause.key(key));yes.own(action)
 esc,normal=normal.branch(normal.key('Escape'));esc.own('OpenPause')
 photo,rest=normal.guarded_mode(1)
 for key,action in [('E','CloseModal'),('F','CloseModal'),('R','FlipPhoto')]:yes,photo=photo.branch(photo.key(key));yes.own(action)
 for key,yaw in [('Left',-2.0),('Right',2.0)]:
  yes,photo=photo.branch(photo.key(key,held=True));yes.call(ACT+'K2_AddActorLocalRotation',**{'self':yes.var('HeldPhoto'),'DeltaRotation':unreal.Rotator(pitch=0,yaw=yaw,roll=0),'bSweep':False,'bTeleport':True})
 document,rest=rest.guarded_mode(2)
 for key in ['E','F']:yes,document=document.branch(document.key(key));yes.own('CloseModal')
 dialogue,rest=rest.guarded_mode(3)
 for key,action in [('One','HandleOne'),('Two','HandleTwo'),('Three','HandleThree'),('E','CloseModal')]:yes,dialogue=dialogue.branch(dialogue.key(key));yes.own(action)
 watch,rest=rest.guarded_mode(4)
 close,watch=watch.branch(watch.key('Q'));close.own('CloseModal')
 confirm,watch=watch.branch(watch.key('E'));testing,confirm=confirm.branch(confirm.var('Testing'));testing.own('CloseModal');confirm.own('ConfirmWatch')
 journal,rest=rest.guarded_mode(5)
 for key in ['Tab','E']:yes,journal=journal.branch(journal.key(key));yes.own('CloseModal')
 exploration,rest=rest.guarded_mode(0)
 for key,action in [('Tab','OpenJournal'),('Q','OpenWatch'),('F','InspectSelected'),('E','Interact')]:yes,exploration=exploration.branch(exploration.key(key));yes.own(action)
 jog,walk=exploration.branch(exploration.key('LeftShift',held=True))
 for node,speed in [(jog,420.0),(walk,260.0)]:
  movement=node.var('CharacterMovement',node.var('Player'),'/Script/Engine.Character');node.set('MaxWalkSpeed',speed,movement,'/Script/Engine.CharacterMovementComponent')
 crouch,rest=walk.branch(walk.key('LeftControl'))
 ducked,standing=crouch.branch(crouch.var('bIsCrouched',crouch.var('Player'),'/Script/Engine.Character'))
 ducked.call(CHAR+'UnCrouch',**{'self':ducked.var('Player')});standing.call(CHAR+'Crouch',**{'self':standing.var('Player')})

 f=fn('UpdateStep')
 f,not_ready=f.branch(f.valid(f.var('Player')));not_ready.own('Initialize')
 talking,other=f.guarded_mode(3)
 distance=talking.data(ACT+'GetDistanceTo',**{'self':talking.var('Player'),'OtherActor':talking.var('MotherActor')})
 away,near=talking.branch(talking.data(MATH+'Greater_DoubleDouble',A=distance,B=350));away.own('CloseModal')
 join=f.g.set('Prompt','');og.link(away.cur,og.pin_in(join));og.link(near.cur,og.pin_in(join));og.link(other.cur,og.pin_in(join));f.cur=og.pin_out(join)
 f.own('InputFrame');f.own('UpdateTarget')
 testing,rest=f.branch(f.var('Testing'));testing.set('TestElapsed',testing.data(MATH+'Add_DoubleDouble',A=testing.var('TestElapsed'),B=f.g.input('DeltaSeconds')))
 done,waiting=testing.branch(testing.data(MATH+'GreaterEqual_DoubleDouble',A=testing.var('TestElapsed'),B=testing.var('CalibrationSeconds')))
 done.set('Testing',False);done.set('WatchCalibrated',True);done.panel(4,'Calibration successful','The final alignment holds. The handmade Chronowatch is ready.\n\nNo camera movement is required. Take a moment, then register the time anchor on the porch.','Q  Close    E  Register when near anchor');done.notice('Final calibration successful.');done.commit()
 active,expired=rest.branch(rest.data(MATH+'Greater_DoubleDouble',A=rest.var('NoticeRemaining'),B=0))
 active.set('NoticeRemaining',active.data(MATH+'Subtract_DoubleDouble',A=active.var('NoticeRemaining'),B=f.g.input('DeltaSeconds')));expired.set('Notice','')

 ev=og.events(bp);ev.editor.remove_nodes(ev.editor.list_all_nodes())
 begin=ev.event('ReceiveBeginPlay');node=ev.call(CLASS+':Initialize');og.chain(begin,node)
 tick=ev.event('ReceiveTick');node=ev.call(CLASS+':UpdateStep');og.link(tick,'DeltaSeconds',node,'DeltaSeconds');og.chain(tick,node)
 end=ev.event('ReceiveEndPlay');node=ev.call(CLASS+':RestorePhoto');og.chain(end,node)
 # UE's promotable operators can reconstruct when their result is connected.
 # Reapply authored scalars only after every connection has settled.
 for _ in range(2):
  for node,pin,value in MATH_LITERALS:og.default(node,pin,value)
 # Runtime manager remains responsive while the real menu pause is active.
 og.compile_bp(bp)
 cdo=unreal.get_default_object(og.L.generated_class(bp));tickprop=cdo.get_editor_property('primary_actor_tick');tickprop.set_editor_property('start_with_tick_enabled',True);tickprop.set_editor_property('tick_even_when_paused',True);cdo.set_editor_property('primary_actor_tick',tickprop)
 report=og.compile_bp(bp,save=True)
 return bp,save,report

def main():
 report={'success':False,'milestone':'A','runtime':'Native Unreal Blueprints','provisional_story_copy':True}
 settings=None;promotion=None
 try:
  settings=unreal.get_default_object(unreal.load_class(None,'/Script/BlueprintGraph.BlueprintEditorSettings'));promotion=settings.get_editor_property('bEnableTypePromotion');settings.set_editor_property('bEnableTypePromotion',False)
  bp,save,compile_report=build_actions()
  from build_opening_hud import build_hud
  hud=build_hud(og.L.generated_class(bp));og.compile_bp(bp,save=True)
  movement_defaults=[]
  for player_path in ['/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter','/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter']:
   player_bp=unreal.load_asset(player_path);player_cdo=unreal.get_default_object(og.L.generated_class(player_bp));movement=player_cdo.get_component_by_class(unreal.CharacterMovementComponent)
   # Preserve the original assets before changing only their crouch capability.
   disk=ROOT/'Content'/Path(player_path.removeprefix('/Game/')+'.uasset');backup=ROOT.parent/'output/opening/original_player_assets'/disk.name;backup.parent.mkdir(parents=True,exist_ok=True)
   if disk.exists() and not backup.exists():backup.write_bytes(disk.read_bytes())
   props=movement.get_editor_property('nav_agent_props');props.set_editor_property('can_crouch',True);movement.set_editor_property('nav_agent_props',props)
   unreal.EditorAssetLibrary.save_loaded_asset(player_bp,False);movement_defaults.append({'asset':player_path,'can_crouch':True})
  from build_opening_scene import build_scene
  scene=build_scene()
  report.update(success=True,manager=compile_report,hud=hud.get_path_name(),save_class=save.get_path_name(),scene=scene,movement_defaults=movement_defaults)
 except Exception:report['error']=traceback.format_exc();raise
 finally:
  if settings is not None and promotion is not None:settings.set_editor_property('bEnableTypePromotion',promotion)
  (ROOT/'opening_build_report.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')

if __name__=='__main__':main()
