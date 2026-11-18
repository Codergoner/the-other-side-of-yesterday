"""Native Blueprint implementation of the user-supplied Chapters 1–2 draft.

Extends the existing Opening actions/HUD/save classes. Python authors assets;
all dialogue, input, transactions and timeline behavior execute native K2 nodes.
"""
from pathlib import Path
import copy, json, sys, traceback, textwrap
import unreal
ROOT=Path(unreal.Paths.project_dir()).resolve();sys.path.insert(0,str(ROOT/'Python'))
import opening_graph as og
import build_opening_actions as base
from build_opening_actions import Flow,PATH,CLASS,SAVE_PATH,SAVE_CLASS,MATH,SYS,GS,ACT,PC,CTL,CAM,CHAR,wrap
CONTENT=json.loads((ROOT/'ContentData/chapters_1_2_dialogue.json').read_text(encoding='utf-8'))
NODES=copy.deepcopy(CONTENT['nodes'])
S='/Script/Engine.KismetStringLibrary.'
ARR='/Script/Engine.KismetArrayLibrary.'
MACRO='/Engine/EditorBlueprintResources/StandardMacros.StandardMacros:ForEachLoop'
NEW_FLAGS=['IntroSeen','PhotoExchangeDone','LetterExchangeDone','OriginalMemorialRead','DepartureDone','NeriMet','HealerMet','HealerTaskOffered','SelaMet','WaterTaken','LinenBundleReady','LinenThanksDone','CanvasRequestKnown','CanvasOffered','CanvasOwned','HealerReportDone','ConsequenceObserved','Chapter2Complete','HasDeparted','HasReturned','ReturnSignalActive','ClinicInspected','HarborInspected']
INT_FIELDS={'MotherOpeningResponse':0,'EraIndex':0,'LinenState':0,'CanvasPlan':0,'StormCover':0,'CurrentChapter':1,'HealerTrust':0,'CalibrationTests':0,'FinalResponse':0}
STRING_FIELDS={'PriorTimelineObservation':'','LatestTimelineObservation':''}
REAL_FIELDS={'ReturnClockSeconds':0}
STATE=list(dict.fromkeys(base.FLAGS+NEW_FLAGS))+list(INT_FIELDS)+list(STRING_FIELDS)+list(REAL_FIELDS)+['TrustEventIds']
REFS=['NeriActor','HealerActor','SelaActor','WaterActor','LinenActor','LinenTrayActor','CanvasActor','ClinicInstallActor','HarborInstallActor','MemorialActor','ClinicRecordActor','HarborRecordActor','ClinicCoverActor','HarborCoverActor','NeriHarborDestinationActor','MotherHomeDestinationActor']
DECLS={
 'StartScene':{'SceneId':'string'},'StartNode':{'NodeId':'string'},'RenderDialogueLine':{},'AdvanceDialogue':{},'ChooseDialogue':{'ChoiceIndex':'int'},'FinishNode':{},'FinishScene':{},'SkipRecollections':{},'CloseDocument':{},'OpenMemorial':{},'OpenHealer':{},'OpenSela':{},'OpenNeri':{},'TakeLinen':{},'DeliverLinen':{},'TakeCanvas':{},'InstallCover':{'Destination':'int'},'AddTrustEvent':{'EventId':'string','Amount':'int'},'RotateDial':{'Direction':'int'},'RenderWatch':{},'BeginTravel':{},'TravelTick':{'DeltaSeconds':'real'},'ApplyWorldState':{},'RestoreSafeScene':{},'SetGroupVisible':{'Actors':og.array_type(og.object_type(unreal.Actor)),'Show':'bool'},'SetVisible':{'Object':og.object_type(unreal.Actor),'Show':'bool'},'StoryTick':{'DeltaSeconds':'real'},'MovementFrame':{},'NpcTick':{'DeltaSeconds':'real'},'ShowPhotoView':{},'ShowLetterDocument':{},'ShowMemorialDocument':{},'ReofferLinen':{},'MapView':{},'RequestPerspective':{},'RequestTimePause':{},'EndSlice':{},'SelectIsland':{'Island':'int'},'RefreshUI':{},'Initialize':{},'SaveProgress':{},'_SaveCopy':{},'LoadProgress':{},'ApplyState':{},'Interact':{},'UpdateTarget':{},'OpenPhoto':{},'OpenLetter':{},'FlipPhoto':{},'OpenMother':{},'UseWorkbench':{},'PickupComponent':{},'ActivateAnchor':{},'OpenWatch':{},'ConfirmWatch':{},'CloseModal':{},'OpenPause':{},'OpenJournal':{},'HandleOne':{},'HandleTwo':{},'HandleThree':{},'InputFrame':{},'UpdateStep':{'DeltaSeconds':'real'},'SetMode':{'NewMode':'int'},'MotherTopic':{},'MotherOfferHelp':{}
}
DECLS.update({'RenderJournal':{},'TurnJournal':{'Direction':'int'}})
DECLS.update({'RestorePlayerCheckpoint':{},'CameraFraming':{'DeltaSeconds':'real'},'OpenHelp':{}})

def eqs(f,a,b):return f.data(S+'EqualEqual_StrStr',A=a,B=b)
def lt(f,a,b):return f.data(MATH+'Less_IntInt',A=a,B=b)
def gt(f,a,b):return f.data(MATH+'Greater_IntInt',A=a,B=b)
def num(f,a,b,op='Add_IntInt'):return f.data(MATH+op,A=a,B=b)
def concat(f,a,b):return f.data(S+'Concat_StrStr',A=a,B=b)
def merge(*flows):
 n=flows[0].g.set('FlowMarker',0)
 for f in flows:og.link(f.cur,og.pin_in(n))
 return Flow(flows[0].g,og.pin_out(n))
def call_visible(f,ref,show):f.own('SetVisible',Object=f.var(ref),Show=show)
def array_item(f,array,index):return og.value_pin(f.call(ARR+'Array_Get',TargetArray=array,Index=index),'Item')
def array_length(f,array):return f.data(ARR+'Array_Length',TargetArray=array)
def node_lines(node):return [wrap(line['speaker']+': '+line['text']) for line in node.get('lines',[])]
def add_node(id,lines,next=None,choices=None,title=None):
 NODES[id]={'id':id,'lines':lines,'next':next or '', 'choices':choices or []}
 if title:NODES[id]['display_title']=title
def line(speaker,text):return {'speaker':speaker,'text':text}

# Short, authored reoffers repeat existing source lines, never regenerated text.
add_node('C2_01.reoffer',[CONTENT['scenes']['C2_01']['opening'][-1]],choices=NODES['C2_01.start']['choices'])
add_node('repeat.mother',[line('Mother','The lamp will be here when you get back.')])
add_node('repeat.healer.pending',[line('Healer',"Sela's parcel should be wrapped and ready.")])
add_node('repeat.healer.done',[line('Healer',"I should get back to work. You're welcome to the water.")])
add_node('repeat.sela.canvas',[line('Sela','You have the only sound sheet. Check the fixings before you settle on a place.')],next='C2_04.choice')
for id,label in [('C1_00.five_years_earlier','Five years earlier'),('C1_00.three_years_earlier','Three years earlier'),('C1_00.one_year_earlier','One year earlier')]:NODES[id]['display_title']=label
for id in ['C1_05.first_test','C1_05.second_test']:NODES[id]['display_title']='RETURN SIGNAL — STABLE'

def build_story():
 bp=og.blueprint(PATH,unreal.Actor);save=og.blueprint(SAVE_PATH,unreal.SaveGame)
 base.MATH_LITERALS.clear()
 for owner in [bp,save]:
  for n in NEW_FLAGS:og.member(owner,n,'bool',False)
  for n,v in INT_FIELDS.items():og.member(owner,n,'int',v)
  for n,v in STRING_FIELDS.items():og.member(owner,n,'string',v)
  for n,v in REAL_FIELDS.items():og.member(owner,n,'real',v)
  og.member(owner,'TrustEventIds',og.array_type('string'))
 for n in REFS+['DialoguePartnerActor']:og.member(bp,n,og.object_type(unreal.Actor),instance_editable=n in REFS)
 for n in ['PastActors','PresentActors','PastCollisionActors']:og.member(bp,n,og.array_type(og.object_type(unreal.Actor)),instance_editable=True)
 for n in ['DialogueNodeId','DialogueRoot','DialogueSpeaker','DialogueLine','NodeNext','ChoiceNext1','ChoiceNext2','ChoiceNext3','ChoiceLabel1','ChoiceLabel2','ChoiceLabel3','PendingDocumentScene','DialogueTitle','DocumentKind']:
  og.member(bp,n,'string','')
 for n in ['DialogueLines','DialogueSpeakers','DialogueTexts']:og.member(bp,n,og.array_type('string'))
 for n in ['DialogueActive','DialogueWaitingChoice','IntroActive','NeriMoving','MotherMoving','MotherToGate','NeriAnimActive','MotherAnimActive','TransitionCommitted','RoutingCamera']:og.member(bp,n,'bool',False)
 for n,v in [('LineIndex',0),('DialogueChoiceCount',0),('SelectedEra',0),('SelectedIsland',0),('PauseReturnMode',0),('PendingEra',0),('PreviousEra',0),('FlowMarker',0),('NeriWaypoint',0),('MotherWaypoint',0)]:og.member(bp,n,'int',v)
 og.member(bp,'JournalPage','int',0)
 og.member(bp,'ContextLabel','string','')
 og.member(bp,'OriginalArmLength','real',300)
 for n,v in [('LineElapsed',0),('MinimumLineSeconds',.75),('TransitionElapsed',0),('LastRealSeconds',0)]:og.member(bp,n,'real',v,instance_editable=n=='MinimumLineSeconds')
 og.member(bp,'WalkAnimation',og.object_type(unreal.AnimSequence),instance_editable=True);og.member(bp,'IdleAnimation',og.object_type(unreal.AnimSequence),instance_editable=True)
 og.member(bp,'PhotoBackInspectionMaterial',og.object_type(unreal.MaterialInterface),instance_editable=True)
 og.compile_bp(save)
 # Keep function identities while replacing only the existing Opening manager.
 for n,args in DECLS.items():
  graph=og.L.find_graph(bp,n)
  if graph:
   ed=og.E.get_graph_editor(graph);ed.remove_nodes([x for x in ed.list_all_nodes() if x.get_class().get_name() not in ['K2Node_FunctionEntry','K2Node_FunctionResult']])
  og.function(bp,n,inputs=args,reset=False)
 og.compile_bp(bp)
 def fn(n):return Flow(og.function(bp,n,reset=False))
 def commit(f,world=False):
  if world:f.own('ApplyWorldState')
  f.own('SaveProgress');f.own('RefreshUI')
 def scene(f,id,partner=None):
  f.set('DialoguePartnerActor',f.var(partner) if partner else None);f.own('StartScene',SceneId=id)
 def copy_state(f,to_save):
  for n in STATE:
   if to_save:f.set(n,f.var(n),f.var('SaveRef'),SAVE_CLASS)
   else:f.set(n,f.var(n,f.var('SaveRef'),SAVE_CLASS))
 def node_start(f,node):f.own('StartNode',NodeId=node)
 def select(conditions,f):
  for cond,action in conditions:
   yes,f=f.branch(cond(f));action(yes)
  return f

 # Readable source-driven dialogue. Choices are UI labels until explicitly chosen.
 f=fn('StartScene');f.set('DialogueRoot',f.g.input('SceneId'));tail=f
 entries={id:data.get('graph_entry') for id,data in CONTENT['scenes'].items() if data.get('graph_entry')}
 entries.update({'C1_00':'C1_00.five_years_earlier','C1_05.identify':'C1_05.identify','C1_05.placed':'C1_05.placed','C1_05.first_test':'C1_05.first_test','C1_05.second_test':'C1_05.second_test','C2_04.healer_request':'C2_04.healer_request','C2_04.shop':'C2_04.shop','C2_04.plan':'C2_04.choice','C2_01.reoffer':'C2_01.reoffer'})
 entries.update({id:id for id in NODES if id.startswith('repeat.')})
 for id,entry in entries.items():
  yes,tail=tail.branch(eqs(tail,tail.g.input('SceneId'),id));node_start(yes,entry)
 for id in ['C2_06','C2_08A','C2_08B']:
  yes,tail=tail.branch(eqs(tail,tail.g.input('SceneId'),id))
  if id=='C2_06':a,b=yes.branch(yes.eq(yes.var('StormCover'),1));node_start(a,'C2_06.clinic');node_start(b,'C2_06.harbor')
  else:a,b=yes.branch(yes.var('OriginalMemorialRead'));node_start(a,id+'.original_memorial_read');node_start(b,id+'.otherwise')
 tail.notice('This conversation is not available.');tail.own('CloseModal')

 f=fn('StartNode');f.set('DialogueNodeId',f.g.input('NodeId'));f.set('DialogueActive',True);f.set('DialogueWaitingChoice',False);f.set('LineIndex',0);f.set('LineElapsed',0);f.set('DialogueChoiceCount',0);tail=f
 for id,data in NODES.items():
  yes,tail=tail.branch(eqs(tail,tail.g.input('NodeId'),id));lines=data.get('lines',[])
  for field,values in [('DialogueLines',node_lines(data)),('DialogueSpeakers',[a['speaker'] for a in lines]),('DialogueTexts',[a['text'] for a in lines])]:yes.set(field,yes.data(S+'ParseIntoArray',SourceString='|||LINE|||'.join(values),Delimiter='|||LINE|||',CullEmptyStrings=True))
  yes.set('NodeNext',data.get('next',''));choices=data.get('choices',[]);yes.set('DialogueChoiceCount',len(choices))
  title=data.get('display_title',CONTENT['scenes'].get(id.split('.')[0],{}).get('title','Conversation'));yes.set('DialogueTitle',title)
  for i in range(3):yes.set('ChoiceLabel'+str(i+1),wrap(choices[i]['label'],62) if i<len(choices) else '');yes.set('ChoiceNext'+str(i+1),choices[i]['next'] if i<len(choices) else '')
  yes.own('RenderDialogueLine')
 tail.set('DialogueActive',False);tail.notice('This conversation is not available.');tail.own('SetMode',NewMode=0)

 f=fn('RenderDialogueLine');f.set('PanelTitle',f.var('DialogueTitle'));f.set('LineElapsed',0)
 more,ended=f.branch(lt(f,f.var('LineIndex'),array_length(f,f.var('DialogueLines'))))
 more.set('DialogueSpeaker',array_item(more,more.var('DialogueSpeakers'),more.var('LineIndex')));more.set('DialogueLine',array_item(more,more.var('DialogueTexts'),more.var('LineIndex')))
 more.set('PanelText',array_item(more,more.var('DialogueLines'),more.var('LineIndex')));more.set('PanelFooter','E  Continue    Esc  Pause');intro,ordinary=more.branch(more.var('IntroActive'));intro.set('PanelFooter','E  Continue    Space  Skip recollections    Esc  Pause');merge(intro,ordinary).own('SetMode',NewMode=3)
 choices,finish=ended.branch(gt(ended,ended.var('DialogueChoiceCount'),0));choices.set('DialogueWaitingChoice',True);choices.set('DialogueSpeaker','');choices.set('DialogueLine','')
 text=concat(choices,'1  ',choices.var('ChoiceLabel1'));second,one=choices.branch(gt(choices,choices.var('DialogueChoiceCount'),1));second.set('PanelText',concat(second,text,concat(second,'\n\n2  ',second.var('ChoiceLabel2'))));one.set('PanelText',text);joined=merge(second,one)
 third,two=joined.branch(gt(joined,joined.var('DialogueChoiceCount'),2));third.set('PanelText',concat(third,third.var('PanelText'),concat(third,'\n\n3  ',third.var('ChoiceLabel3'))));joined=merge(third,two);joined.set('PanelFooter','1 / 2 / 3  Choose    Esc  Pause');joined.own('SetMode',NewMode=3)
 finish.own('FinishNode')

 f=fn('AdvanceDialogue');ok,no=f.branch(f.and_(f.var('DialogueActive'),f.not_(f.var('DialogueWaitingChoice'))));ready,wait=ok.branch(ok.data(MATH+'GreaterEqual_DoubleDouble',A=ok.var('LineElapsed'),B=ok.var('MinimumLineSeconds')))
 ready.set('LineIndex',num(ready,ready.var('LineIndex'),1));ready.own('RenderDialogueLine')

 f=fn('ChooseDialogue');ok,no=f.branch(f.and_(f.var('DialogueActive'),f.var('DialogueWaitingChoice')));valid,no=ok.branch(ok.and_(ok.data(MATH+'GreaterEqual_IntInt',A=ok.g.input('ChoiceIndex'),B=1),ok.data(MATH+'LessEqual_IntInt',A=ok.g.input('ChoiceIndex'),B=ok.var('DialogueChoiceCount'))));tail=valid
 for id,data in NODES.items():
  if not data.get('choices'):continue
  yes,tail=tail.branch(eqs(tail,tail.var('DialogueNodeId'),id));option=yes
  for i,c in enumerate(data['choices'],1):
   chosen,option=option.branch(option.eq(option.g.input('ChoiceIndex'),i))
   if id=='C1_04.start':chosen.set('MotherOpeningResponse',i)
   if id=='C2_01.start' or id=='C2_01.reoffer':
    chosen.set('HealerTaskOffered',True)
    if i==1:chosen.set('LinenState',1)
   if id=='C2_04.choice':chosen.set('CanvasPlan',i if i<3 else 0)
   if id=='C2_09.start':chosen.set('FinalResponse',i)
   chosen.own('SaveProgress');node_start(chosen,c['next'])

 f=fn('FinishNode');tail=f
 for id,data in NODES.items():
  yes,tail=tail.branch(eqs(tail,tail.var('DialogueNodeId'),id))
  # Item consumption/history is intentionally NOT inferred from dialogue metadata.
  flags={
   'C1_01.start':['PhotoSeen','PhotoExchangeDone'],'C1_02.start':['LetterRead','LetterExchangeDone'],'C1_04.continuation':['MotherSpoken'],
   'C1_00.one_year_earlier':['IntroSeen'],'C1_05.identify':['RepairIdentified'],'C1_05.second_test':['WatchCalibrated'],
   'C1_07.start':['OriginalMemorialRead'],'C2_00.continuation':['NeriMet'],'C2_02.start':['LinenBundleReady'],'C2_03.start':['LinenThanksDone'],
   'C2_04.healer_request':['CanvasRequestKnown'],'C2_04.choice_A':['CanvasOffered'],'C2_04.choice_B':['CanvasOffered'],'C2_04.choice_C':['CanvasOffered'],
   'C2_06.continuation':['HealerReportDone'],'C2_08A.continuation':['ConsequenceObserved'],'C2_08B.continuation':['ConsequenceObserved'],'C2_09.continuation':['Chapter2Complete']}.get(id,[])
  for flag in flags:yes.set(flag,True)
  if id=='C1_00.one_year_earlier':yes.set('IntroActive',False)
  if id=='C1_05.second_test':yes.set('MotherMoving',True);yes.set('MotherToGate',True);yes.set('MotherWaypoint',0)
  if id=='C1_07.start':yes.set('PriorTimelineObservation',CONTENT['scenes']['C1_07']['documents']['plaque'])
  if id=='C2_00.continuation':yes.set('NeriMoving',True);yes.set('NeriWaypoint',0)
  if id.startswith('C1_08.choice_'):yes.set('DepartureDone',True)
  if id=='C2_09.continuation':
   prior,other=yes.branch(yes.var('OriginalMemorialRead'));prior.set('LatestTimelineObservation',CONTENT['scenes']['C2_09']['documents']['journal_prior']);other.set('LatestTimelineObservation',CONTENT['scenes']['C2_09']['documents']['journal_otherwise']);yes=merge(prior,other)
  commit(yes,world=True)
  if id=='C2_04.shop':
   original,other=yes.branch(yes.var('OriginalMemorialRead'));node_start(original,'C2_04.memorial_callback');node_start(other,'C2_04.choice')
  elif data.get('next'):node_start(yes,data['next'])
  else:yes.own('FinishScene')

 f=fn('FinishScene');f.set('DialogueActive',False);f.set('DialogueWaitingChoice',False);f.set('DialoguePartnerActor',None);f.own('SetMode',NewMode=0);f.own('RefreshUI');tail=f
 for root,action in [('C1_01','ShowPhotoView'),('C1_08','OpenWatch'),('C2_07','OpenWatch'),('C2_09','EndSlice')]:yes,tail=tail.branch(eqs(tail,tail.var('DialogueRoot'),root));yes.own(action)
 changed,rest=tail.branch(tail.or_(eqs(tail,tail.var('DialogueRoot'),'C2_08A'),eqs(tail,tail.var('DialogueRoot'),'C2_08B')));start,done=changed.branch(changed.not_(changed.var('Chapter2Complete')));start.set('MotherMoving',True);start.set('MotherToGate',False);start.set('MotherWaypoint',0)
 f=fn('SkipRecollections');yes,no=f.branch(f.var('IntroActive'));yes.set('IntroSeen',True);yes.set('IntroActive',False);yes.set('DialogueActive',False);yes.own('CloseModal');commit(yes)

 # Save/load keeps old aliases and stable slot; transient conversations never auto-select.
 f=fn('_SaveCopy');copy_state(f,True);f.set('Chapter',f.var('CurrentChapter'),f.var('SaveRef'),SAVE_CLASS);f.set('SchemaVersion',2,f.var('SaveRef'),SAVE_CLASS)
 past,present=f.branch(f.eq(f.var('EraIndex'),1));past.set('Era','Past',past.var('SaveRef'),SAVE_CLASS);past.set('SafeLocationId','past.gate',past.var('SaveRef'),SAVE_CLASS);present.set('Era','Present',present.var('SaveRef'),SAVE_CLASS)
 home,gate=present.branch(present.or_(present.var('Chapter2Complete'),present.and_(present.not_(present.var('HasDeparted')),present.not_(present.var('WatchCalibrated')))));home.set('SafeLocationId','present.home',home.var('SaveRef'),SAVE_CLASS);gate.set('SafeLocationId','present.gate',gate.var('SaveRef'),SAVE_CLASS);f=merge(past,home,gate)
 result=f.call(GS+'SaveGameToSlot',SaveGameObject=f.var('SaveRef'),SlotName=f.var('SaveSlot'),UserIndex=0);f.set('SaveSucceeded',og.value_pin(result));ok,bad=f.branch(f.var('SaveSucceeded'));bad.notice('Progress is still in this session, but the save could not be written.')
 f=fn('SaveProgress');busy,allowed=f.guarded_mode(7)
 exists,missing=allowed.branch(allowed.valid(allowed.var('SaveRef')));created=missing.call(GS+'CreateSaveGameObject',SaveGameClass=SAVE_CLASS);missing.set('SaveRef',og.value_pin(created));exists.own('_SaveCopy');missing.own('_SaveCopy')
 f=fn('LoadProgress');f.own('RestorePhoto');f.set('DialogueActive',False);f.set('DialogueWaitingChoice',False);f.set('IntroActive',False);f.set('Testing',False);f.set('NeriMoving',False);f.set('MotherMoving',False);f.call(GS+'SetGamePaused',bPaused=False);f.own('SetMode',NewMode=0)
 exists,new=f.branch(f.data(GS+'DoesSaveGameExist',SlotName=f.var('SaveSlot'),UserIndex=0));loaded=exists.call(GS+'LoadGameFromSlot',SlotName=exists.var('SaveSlot'),UserIndex=0);cast=exists.g.cast(SAVE_CLASS,og.value_pin(loaded));og.link(exists.cur,og.pin_in(cast));exists.cur=og.pin_out(cast);exists.set('SaveRef',exists.g.cast_value(cast));copy_state(exists,False)
 legacy,modern=exists.branch(lt(exists,exists.var('SchemaVersion',exists.var('SaveRef'),SAVE_CLASS),2));progress=legacy.or_(legacy.var('PhotoSeen'),legacy.or_(legacy.var('LetterRead'),legacy.or_(legacy.var('MotherSpoken'),legacy.var('WatchCalibrated'))));legacy.set('IntroSeen',progress);legacy.set('PhotoExchangeDone',legacy.var('PhotoSeen'));legacy.set('LetterExchangeDone',legacy.var('LetterRead'));cal,uncal=legacy.branch(legacy.var('WatchCalibrated'));cal.set('CalibrationTests',2);exists=merge(cal,uncal,modern)
 exists.own('RestoreSafeScene');exists.own('RestorePlayerCheckpoint');exists.own('ApplyWorldState');exists.own('RefreshUI');exists.notice('Committed progress restored at its safe checkpoint.')
 fresh=new.call(GS+'CreateSaveGameObject',SaveGameClass=SAVE_CLASS);new.set('SaveRef',og.value_pin(fresh));new.own('RestoreSafeScene');new.own('ApplyWorldState');new.own('RefreshUI');new.set('IntroActive',True);scene(new,'C1_00')
 failed=Flow(f.g,og.pin_out(cast,'CastFailed'));failed.own('RestoreSafeScene');failed.own('ApplyWorldState');failed.notice('This save could not be loaded. It has not been overwritten.')
 f=fn('RestorePlayerCheckpoint');home,gate=f.branch(f.and_(f.eq(f.var('EraIndex'),0),f.or_(f.var('Chapter2Complete'),f.and_(f.not_(f.var('HasDeparted')),f.not_(f.var('WatchCalibrated'))))))
 for flow,where in [(home,unreal.Vector(-620,1240,1107)),(gate,unreal.Vector(120,1240,991))]:flow.call(ACT+'K2_SetActorLocation',**{'self':flow.var('Player'),'NewLocation':where,'bSweep':False,'bTeleport':True})

 # Era presentation is bounded and derives entirely from saved authoritative state.
 f=fn('SetVisible');obj=f.g.input('Object');yes,no=f.branch(f.valid(obj));yes.call(ACT+'SetActorHiddenInGame',**{'self':obj,'bNewHidden':yes.not_(yes.g.input('Show'))});blocking=yes.or_(yes.tag(obj,'Opening.Interactable'),yes.or_(yes.tag(obj,'Opening.Blocking'),yes.tag(obj,'Opening.OriginalCollision')));yes.call(ACT+'SetActorEnableCollision',**{'self':obj,'bNewActorEnableCollision':yes.and_(yes.g.input('Show'),blocking)})
 f=fn('SetGroupVisible');loop=f.g._node(f.g.editor.add_macro_node(MACRO),'ForEachLoop');og.link(f.cur,og.pin_in(loop,'Exec'));og.link(f.g.input('Actors'),og.pin_in(loop,'Array'));body=Flow(f.g,og.pin_out(loop,'LoopBody'));body.own('SetVisible',Object=og.value_pin(loop,'Array Element'),Show=body.g.input('Show'))
 f=fn('ApplyWorldState');past=f.eq(f.var('EraIndex'),1);present=f.not_(past);f.own('SetGroupVisible',Actors=f.var('PastActors'),Show=past);f.own('SetGroupVisible',Actors=f.var('PresentActors'),Show=present)
 for ref,state in [('ClinicCoverActor',f.and_(past,f.eq(f.var('StormCover'),1))),('HarborCoverActor',f.and_(past,f.eq(f.var('StormCover'),2))),('ClinicRecordActor',f.and_(present,f.eq(f.var('StormCover'),1))),('HarborRecordActor',f.and_(present,f.eq(f.var('StormCover'),2)))]:call_visible(f,ref,state)
 call_visible(f,'LinenActor',f.and_(past,f.and_(f.eq(f.var('LinenState'),1),f.var('LinenBundleReady'))))
 call_visible(f,'CanvasActor',f.and_(past,f.and_(f.var('CanvasOffered'),f.and_(f.not_(f.var('CanvasOwned')),f.eq(f.var('StormCover'),0)))))
 call_visible(f,'ComponentActor',f.and_(present,f.and_(f.not_(f.var('ComponentCollected')),f.not_(f.var('ComponentPlaced')))))
 call_visible(f,'DrawerActor',False)
 f=fn('ApplyState');f.own('ApplyWorldState')
 f=fn('RestoreSafeScene');f.set('LastRealSeconds',f.data(GS+'GetRealTimeSeconds'));f.set('TransitionCommitted',False);f.set('TransitionElapsed',0);f.set('NeriMoving',False);f.set('MotherMoving',False);f.set('NeriAnimActive',False);f.set('MotherAnimActive',False)
 for ref in ['NeriActor','MotherActor']:
  mesh=f.data(ACT+'GetComponentByClass',**{'self':f.var(ref),'ComponentClass':'/Script/Engine.SkeletalMeshComponent'});f.call('/Script/Engine.SkeletalMeshComponent.PlayAnimation',**{'self':mesh,'NewAnimToPlay':f.var('IdleAnimation'),'bLooping':True})
 neri_done,neri_new=f.branch(f.var('NeriMet'))
 neri_done.call(ACT+'K2_SetActorLocation',**{'self':neri_done.var('NeriActor'),'NewLocation':unreal.Vector(120,-570,1077),'bSweep':False,'bTeleport':True});neri_new.call(ACT+'K2_SetActorLocation',**{'self':neri_new.var('NeriActor'),'NewLocation':unreal.Vector(120,1050,915),'bSweep':False,'bTeleport':True});f=merge(neri_done,neri_new)
 returned,initial=f.branch(f.and_(f.var('HasReturned'),f.not_(f.var('ConsequenceObserved'))));returned.call(ACT+'K2_SetActorLocation',**{'self':returned.var('MotherActor'),'NewLocation':unreal.Vector(-420,1340,1011),'bSweep':False,'bTeleport':True});atgate,initial=initial.branch(initial.and_(initial.var('WatchCalibrated'),initial.not_(initial.var('HasReturned'))));atgate.call(ACT+'K2_SetActorLocation',**{'self':atgate.var('MotherActor'),'NewLocation':unreal.Vector(-40,1240,896),'bSweep':False,'bTeleport':True});initial.call(ACT+'K2_SetActorLocation',**{'self':initial.var('MotherActor'),'NewLocation':unreal.Vector(-915,1412,1011),'bSweep':False,'bTeleport':True})

 # Home objects and two authored calibration tests.
 f=fn('OpenPhoto');f.set('HomeExplored',True);seen,first=f.branch(f.var('PhotoExchangeDone'));seen.own('ShowPhotoView');scene(first,'C1_01','PhotoActor')
 f=fn('ShowPhotoView');f.set('PhotoBack',False);f.set('HeldPhoto',f.var('PhotoActor'));f.set('PhotoReturn',f.data(ACT+'GetTransform',**{'self':f.var('HeldPhoto')}));mesh=f.data(ACT+'GetComponentByClass',**{'self':f.var('HeldPhoto'),'ComponentClass':'/Script/Engine.StaticMeshComponent'});f.set('PhotoOriginalMaterial',f.data('/Script/Engine.PrimitiveComponent.GetMaterial',**{'self':mesh,'ElementIndex':0}));f.call('/Script/Engine.PrimitiveComponent.SetMaterial',**{'self':mesh,'ElementIndex':0,'Material':f.var('InspectionMaterial')});f.call(ACT+'SetActorEnableCollision',**{'self':f.var('HeldPhoto'),'bNewActorEnableCollision':False})
 loc=f.data(CAM+'GetCameraLocation',**{'self':f.var('Camera')});rot=f.data(CAM+'GetCameraRotation',**{'self':f.var('Camera')});fw=f.data(MATH+'GetForwardVector',InRot=rot);right=f.data(MATH+'GetRightVector',InRot=rot);position=f.data(MATH+'Add_VectorVector',A=f.data(MATH+'Add_VectorVector',A=loc,B=f.data(MATH+'Multiply_VectorFloat',A=fw,B=75)),B=f.data(MATH+'Multiply_VectorFloat',A=right,B=-23))
 f.call(ACT+'K2_SetActorLocation',**{'self':f.var('HeldPhoto'),'NewLocation':position,'bSweep':False,'bTeleport':True});f.call(ACT+'K2_SetActorRotation',**{'self':f.var('HeldPhoto'),'NewRotation':f.data(MATH+'FindLookAtRotation',Start=position,Target=loc),'bTeleportPhysics':True});f.panel(1,'Family photograph','Mother holds you as a baby. Your father took the photograph.','R  Turn over    Left / Right  Rotate\nE / F  Put back    Esc  Pause')
 f=fn('FlipPhoto');yes,no=f.guarded_mode(1);yes.set('PhotoBack',yes.not_(yes.var('PhotoBack')));yes.call(ACT+'K2_AddActorLocalRotation',**{'self':yes.var('HeldPhoto'),'DeltaRotation':unreal.Rotator(pitch=0,yaw=180,roll=0),'bSweep':False,'bTeleport':True});back,front=yes.branch(yes.var('PhotoBack'));back.set('PhotoBackSeen',True);back.set('PanelText','Writing on the back:\n\nOur first summer at home.');commit(back);front.set('PanelText','Mother holds you as a baby. Your father took the photograph.')
 for flow,material in [(back,'PhotoBackInspectionMaterial'),(front,'InspectionMaterial')]:
  mesh=flow.data(ACT+'GetComponentByClass',**{'self':flow.var('HeldPhoto'),'ComponentClass':'/Script/Engine.StaticMeshComponent'});flow.call('/Script/Engine.PrimitiveComponent.SetMaterial',**{'self':mesh,'ElementIndex':0,'Material':flow.var(material)})
 f=fn('OpenLetter');f.own('ShowLetterDocument')
 f=fn('ShowLetterDocument');f.set('DocumentKind','letter');new,old=f.branch(f.not_(f.var('LetterExchangeDone')));new.set('PendingDocumentScene','C1_02');old.set('PendingDocumentScene','');f=merge(new,old);f.panel(2,'The unsent letter',CONTENT['scenes']['C1_02']['documents']['letter'],'E  Continue / Close    Esc  Pause')
 f=fn('CloseDocument');next_,close=f.branch(f.not_(eqs(f,f.var('PendingDocumentScene'),'')));letter,mem=next_.branch(eqs(next_,next_.var('PendingDocumentScene'),'C1_02'));letter.set('DialoguePartnerActor',letter.var('LetterActor'));mem.set('DialoguePartnerActor',mem.var('MemorialActor'));next_=merge(letter,mem);next_.own('StartScene',SceneId=next_.var('PendingDocumentScene'));next_.set('PendingDocumentScene','');close.own('CloseModal')
 f=fn('OpenMother');f.set('MotherMet',True);finished,rest=f.branch(f.var('Chapter2Complete'));finished.notice('Chapters 1–2 complete. The family room remains available.')
 ending,rest=rest.branch(rest.and_(rest.var('ConsequenceObserved'),rest.eq(rest.var('EraIndex'),0)));inside,walking=ending.branch(ending.and_(ending.not_(ending.var('MotherMoving')),ending.data(MATH+'LessEqual_DoubleDouble',A=ending.data(ACT+'GetDistanceTo',**{'self':ending.var('MotherActor'),'OtherActor':ending.var('MotherHomeDestinationActor')}),B=90)));scene(inside,'C2_09','MotherActor');walking.notice('Follow Mother into the surviving family room.')
 done,rest=rest.branch(rest.var('MotherSpoken'));scene(done,'repeat.mother','MotherActor')
 ready,early=rest.branch(rest.and_(rest.var('PhotoSeen'),rest.var('LetterRead')));scene(ready,'C1_04','MotherActor');scene(early,'C1_03','MotherActor')
 f=fn('MotherTopic');f.own('ChooseDialogue',ChoiceIndex=1)
 f=fn('MotherOfferHelp');f.own('ChooseDialogue',ChoiceIndex=2)
 f=fn('UseWorkbench');ready,no=f.branch(f.var('MotherSpoken'));no.notice('Speak with Mother before the final test.')
 calibrated,rest=ready.branch(ready.var('WatchCalibrated'));calibrated.own('OpenWatch')
 identified,rest=rest.branch(rest.var('RepairIdentified'));scene(rest,'C1_05.identify','BenchActor')
 placed,needs=identified.branch(identified.var('ComponentPlaced'));held,missing=needs.branch(needs.var('ComponentCollected'));held.set('ComponentPlaced',True);commit(held,world=True);scene(held,'C1_05.placed','BenchActor');missing.notice('The prepared contact is in the dish beside the watch.')
 tested,test=placed.branch(placed.data(MATH+'GreaterEqual_IntInt',A=placed.var('CalibrationTests'),B=2));scene(tested,'C1_05.second_test','BenchActor');test.set('Testing',True);test.set('TestElapsed',0);test.panel(4,'Final calibration','Testing the secured contact.\n\nClosing this view safely cancels an unfinished test.','Q / E  Cancel    Esc  Pause')
 f=fn('PickupComponent');okay,no=f.branch(f.and_(f.var('RepairIdentified'),f.and_(f.not_(f.var('ComponentCollected')),f.not_(f.var('ComponentPlaced')))));okay.set('ComponentCollected',True);okay.notice('Prepared contact taken. Fit it at the workbench.');commit(okay,world=True);no.notice('Examine the contact seat at the workbench first.')

 # Past NPCs, explicit physical quest transactions, and reversible plans.
 f=fn('OpenNeri');met,new=f.branch(f.var('NeriMet'));met.notice('The clinic is along the street; its blue shutters are visible.');scene(new,'C2_00','NeriActor')
 f=fn('OpenHealer');f.set('HealerMet',True);met,no=f.branch(f.var('NeriMet'));no.notice('Speak with the local resident at the gate first.')
 report,rest=met.branch(met.and_(gt(met,met.var('StormCover'),0),met.not_(met.var('HealerReportDone'))));scene(report,'C2_06','HealerActor')
 exhausted,rest=rest.branch(rest.var('HealerReportDone'));scene(exhausted,'repeat.healer.done','HealerActor')
 delivered,rest=rest.branch(rest.eq(rest.var('LinenState'),3));thanks,request=delivered.branch(delivered.not_(delivered.var('LinenThanksDone')));scene(thanks,'C2_03','HealerActor');newrequest,asked=request.branch(request.not_(request.var('CanvasRequestKnown')));scene(newrequest,'C2_04.healer_request','HealerActor');asked.notice('Sela has the waterproof sheet. Look at both sets of fixings before installing it.')
 pending,rest=rest.branch(gt(rest,rest.var('LinenState'),0));scene(pending,'repeat.healer.pending','HealerActor');offered,first=rest.branch(rest.var('HealerTaskOffered'));scene(offered,'C2_01.reoffer','HealerActor');scene(first,'C2_01','HealerActor')
 f=fn('ReofferLinen');scene(f,'C2_01.reoffer','HealerActor')
 f=fn('OpenSela');f.set('SelaMet',True);committed,f=f.branch(gt(f,f.var('StormCover'),0));committed.notice('The single sheet is installed. The recorded choice remains committed.');accepted,rest=f.branch(f.eq(f.var('LinenState'),1));ready,intro=accepted.branch(accepted.var('LinenBundleReady'));ready.notice('Take the marked wrapped linen from the counter.');scene(intro,'C2_02','SelaActor')
 canvas,rest=rest.branch(rest.and_(rest.eq(rest.var('LinenState'),3),rest.var('CanvasRequestKnown')));owned,unowned=canvas.branch(canvas.var('CanvasOwned'));scene(owned,'repeat.sela.canvas','SelaActor');offered,first=unowned.branch(unowned.var('CanvasOffered'));scene(offered,'C2_04.plan','SelaActor');scene(first,'C2_04.shop','SelaActor');rest.notice('The clinic is across the square. Speak with the Healer there.')
 f=fn('TakeLinen');valid,no=f.branch(f.and_(f.eq(f.var('LinenState'),1),f.var('LinenBundleReady')));valid.set('LinenState',2);valid.notice('Wrapped clinic linen collected. Deliver it to the clinic tray.');commit(valid,world=True);no.notice('There is no uncollected clinic parcel here.')
 f=fn('DeliverLinen');owned,no=f.branch(f.eq(f.var('LinenState'),2));owned.set('LinenState',3);owned.own('AddTrustEvent',EventId='trust.healer.linen_delivered',Amount=10);commit(owned,world=True);scene(owned,'C2_03','HealerActor');no.notice('The clinic tray needs the wrapped parcel from Sela.')
 f=fn('TakeCanvas');valid,no=f.branch(f.and_(f.var('CanvasOffered'),f.and_(f.not_(f.var('CanvasOwned')),f.eq(f.var('StormCover'),0))));valid.set('CanvasOwned',True);valid.notice('One waterproof sheet and its supplied fasteners collected.');commit(valid,world=True);no.notice('There is only one sound sheet for this task.')
 f=fn('InstallCover');open_,committed=f.branch(f.eq(f.var('StormCover'),0));committed.notice('The sheet is already installed. This history is committed.')
 held,no=open_.branch(open_.var('CanvasOwned'));no.notice('Inspect the fixings; a full waterproof sheet is needed here.')
 planned,change=held.branch(held.eq(held.var('CanvasPlan'),held.g.input('Destination')));change.set('CanvasPlan',change.g.input('Destination'));change.notice('Plan changed. Interact with these fixings again to install and commit.');commit(change)
 planned.set('StormCover',planned.g.input('Destination'));planned.set('CanvasOwned',False);planned.own('AddTrustEvent',EventId='trust.healer.cover_installed',Amount=20);commit(planned,world=True);clinic,harbor=planned.branch(planned.eq(planned.g.input('Destination'),1));scene(clinic,'C2_05A','ClinicInstallActor');scene(harbor,'C2_05B','HarborInstallActor')
 f=fn('AddTrustEvent');repeat,new=f.branch(f.data(ARR+'Array_Contains',TargetArray=f.var('TrustEventIds'),ItemToFind=f.g.input('EventId')));new.call(ARR+'Array_AddUnique',TargetArray=new.var('TrustEventIds'),NewItem=new.g.input('EventId'));new.set('HealerTrust',new.data(MATH+'Clamp',Value=num(new,new.var('HealerTrust'),new.g.input('Amount')),Min=0,Max=100))

 # Memorial wording is a prior observation, never silently rewritten on return.
 f=fn('OpenMemorial');present,past=f.branch(f.eq(f.var('EraIndex'),0));present.own('ShowMemorialDocument');past.notice('There is no historical display on this wall in this era.')
 f=fn('ShowMemorialDocument');f,past=f.branch(f.eq(f.var('EraIndex'),0));past.notice('There is no historical display on this wall in this era.');f.set('DocumentKind','memorial');original,changed=f.branch(f.eq(f.var('StormCover'),0));seen,new=original.branch(original.var('OriginalMemorialRead'));seen.set('PendingDocumentScene','');new.set('PendingDocumentScene','C1_07');original=merge(seen,new);original.panel(2,'The memorial beside the gate',CONTENT['scenes']['C1_07']['documents']['plaque'],'E  Continue / Close    Esc  Pause')
 clinic,harbor=changed.branch(changed.eq(changed.var('StormCover'),1))
 for dest,id in [(clinic,'C2_08A'),(harbor,'C2_08B')]:
  done,new=dest.branch(dest.var('ConsequenceObserved'));done.set('PendingDocumentScene','');new.set('PendingDocumentScene',id);dest=merge(done,new);dest.panel(2,'The preserved record',CONTENT['scenes'][id]['documents']['caption'],'E  Continue / Close    Esc  Pause')

 # Watch input selects; confirmation at the shared gate is the only travel action.
 f=fn('ActivateAnchor');ready,no=f.branch(f.var('WatchCalibrated'));no.notice('The return signal needs its final two stable tests.')
 ready.set('AnchorActivated',True);commit(ready);present,past=ready.branch(ready.eq(ready.var('EraIndex'),0));done,new=present.branch(present.var('DepartureDone'));arrived,walking=new.branch(new.not_(new.var('MotherMoving')));arrived.set('SelectedEra',1);scene(arrived,'C1_08','MotherActor');walking.notice('Mother is coming to the gate. Wait for her before leaving.');done.set('SelectedEra',1);done.own('OpenWatch');ready,no=past.branch(past.var('HealerReportDone'));ready.set('SelectedEra',0);scene(ready,'C2_07','AnchorActor');no.notice('Finish the current delivery, installation and report before returning.')
 f=fn('OpenWatch');f.own('RestorePhoto');f.set('Testing',False);f.own('RenderWatch')
 f=fn('RotateDial');later,earlier=f.branch(gt(f,f.g.input('Direction'),0));later.set('SelectedEra',0);earlier.set('SelectedEra',1);merge(later,earlier).own('RenderWatch')
 f=fn('RenderWatch');f.set('PanelTitle','Chronowatch');f.set('PanelFooter','Wheel / Left–Right  Select era    E  Confirm\nM  Discovered map    1–4  Islands    Q  Close')
 calibrated,locked=f.branch(f.var('WatchCalibrated'));locked.set('PanelText','Final calibration unfinished. Secure the prepared contact and complete both stable tests.');locked.own('SetMode',NewMode=4)
 past,present=calibrated.branch(calibrated.eq(calibrated.var('SelectedEra'),1));past.set('PanelText','VERDANT — BEFORE THE WAR\nRETURN SIGNAL — CONNECTED\nCONFIRM TRANSITION');present.set('PanelText','RETURN SIGNAL — AVAILABLE\nHOME — PRESENT\nCONFIRM TRANSITION');f=merge(past,present)
 used,open_=f.branch(f.and_(f.eq(f.var('EraIndex'),0),f.var('HasDeparted')));used.set('PanelText','FIRST EXCURSION — COMPLETE\nHOME — PRESENT\nReturn to Mother. This passage cannot be replayed.');used.set('PanelFooter','M  Discovered map    1–4  Islands    Q  Close')
 pending,available=open_.branch(open_.and_(open_.eq(open_.var('EraIndex'),1),open_.not_(open_.var('HealerReportDone'))));pending.set('PanelText','VERDANT — BEFORE THE WAR\nRETURN SIGNAL — CONNECTED\nHome clock running. Finish the task and report to the Healer\nbefore following the guided return signal.');pending.set('PanelFooter','M  Discovered map    1–4  Islands    Q  Close');f=merge(used,pending,available)
 f.set('PanelText',concat(f,f.var('PanelText'),'\n\nISLANDS: Verdant / Ironreach (locked)\nTidehaven (locked) / Ashen Coast (locked)\nPerspective unavailable — relationship not yet ready.\nOptional time-pause test is unavailable.'))
 f.set('PanelText',concat(f,concat(f,f.var('PanelText'),'\nReturn clock (seconds away): '),f.data(S+'Conv_IntToString',InInt=f.data(MATH+'FTrunc',A=f.var('ReturnClockSeconds')))))
 f.own('SetMode',NewMode=4)
 f=fn('SelectIsland');home,other=f.branch(f.eq(f.g.input('Island'),1));home.set('SelectedIsland',0);home.notice('Verdant selected.');other.notice('Island locked — no anchor has been discovered there.')
 f=fn('RequestPerspective');f.notice('PERSPECTIVE UNAVAILABLE — RELATIONSHIP NOT YET READY')
 f=fn('RequestTimePause');f.notice('Optional time-pause test unavailable. It is not required for departure.')
 f=fn('ConfirmWatch');used,f=f.branch(f.and_(f.eq(f.var('EraIndex'),0),f.var('HasDeparted')));used.notice('The first excursion is complete. Return home to Mother; this passage cannot be replayed.');valid,no=f.branch(f.and_(f.var('WatchCalibrated'),f.var('AnchorActivated')));no.notice('Complete calibration and register the gate anchor first.')
 near,far=valid.branch(valid.data(MATH+'LessEqual_DoubleDouble',A=valid.data(ACT+'GetDistanceTo',**{'self':valid.var('Player'),'OtherActor':valid.var('AnchorActor')}),B=260));far.notice('Travel requires the gate anchor.')
 clear,blocked=near.branch(near.data(CTL+'LineOfSightTo',**{'self':near.var('Controller'),'Other':near.var('AnchorActor'),'bAlternateChecks':False}));blocked.notice('A clear view of the gate anchor is required.')
 same,different=clear.branch(clear.eq(clear.var('SelectedEra'),clear.var('EraIndex')));same.notice('The dial is already set to the current era.')
 done,continue_=different.branch(different.var('Chapter2Complete'));done.notice('Chapters 1–2 complete. No later excursion is authored.')
 to_past,to_present=continue_.branch(continue_.eq(continue_.var('SelectedEra'),1));depart,first=to_past.branch(to_past.var('DepartureDone'));depart.own('BeginTravel');first.own('ActivateAnchor')
 reported,pending=to_present.branch(to_present.var('HealerReportDone'));reported.own('BeginTravel');pending.notice('Complete the shelter task and report back before following the return signal.')
 f=fn('BeginTravel');f.own('RestorePhoto');f.set('DialogueActive',False);f.set('Testing',False);f.own('SaveProgress');f.set('PreviousEra',f.var('EraIndex'));f.set('PendingEra',f.var('SelectedEra'));f.set('TransitionElapsed',0);f.set('TransitionCommitted',False);f.own('SetMode',NewMode=7);f.call(CAM+'StartCameraFade',**{'self':f.var('Camera'),'FromAlpha':0,'ToAlpha':1,'Duration':.35,'Color':unreal.LinearColor(0,0,0,1),'bShouldFadeAudio':False,'bHoldWhenFinished':True})
 f=fn('TravelTick');active,no=f.guarded_mode(7);active.set('TransitionElapsed',active.data(MATH+'Add_DoubleDouble',A=active.var('TransitionElapsed'),B=active.g.input('DeltaSeconds')));ready,wait=active.branch(active.data(MATH+'GreaterEqual_DoubleDouble',A=active.var('TransitionElapsed'),B=.4));done,restore=ready.branch(ready.var('TransitionCommitted'))
 safe,bad=restore.branch(restore.and_(restore.valid(restore.var('Player')),restore.valid(restore.var('AnchorActor'))));bad.call(CAM+'StartCameraFade',**{'self':bad.var('Camera'),'FromAlpha':1,'ToAlpha':0,'Duration':.35,'Color':unreal.LinearColor(0,0,0,1),'bShouldFadeAudio':False,'bHoldWhenFinished':False});bad.own('SetMode',NewMode=0);bad.notice('The destination could not be restored. Progress is unchanged.')
 safe.set('EraIndex',safe.var('PendingEra'));safe.own('RestoreSafeScene');safe.own('ApplyWorldState');moved=safe.call(ACT+'K2_SetActorLocation',**{'self':safe.var('Player'),'NewLocation':unreal.Vector(120,1240,991),'bSweep':False,'bTeleport':True});success,failed=safe.branch(og.value_pin(moved,'ReturnValue'))
 past,present=success.branch(success.eq(success.var('EraIndex'),1));past.set('HasDeparted',True);past.set('ReturnSignalActive',True);past.set('CurrentChapter',2);present.set('HasReturned',True);present.set('ReturnSignalActive',False);success=merge(past,present);success.own('RestoreSafeScene');success.set('TransitionCommitted',True);success.set('TransitionElapsed',.45)
 failed.set('EraIndex',failed.var('PreviousEra'));failed.own('ApplyWorldState');failed.call(CAM+'StartCameraFade',**{'self':failed.var('Camera'),'FromAlpha':1,'ToAlpha':0,'Duration':.35,'Color':unreal.LinearColor(0,0,0,1),'bShouldFadeAudio':False,'bHoldWhenFinished':False});failed.own('SetMode',NewMode=0);failed.notice('The safe destination was unavailable. The previous era has been restored.')
 finished,hold=done.branch(done.data(MATH+'GreaterEqual_DoubleDouble',A=done.var('TransitionElapsed'),B=.8));finished.call(CAM+'StartCameraFade',**{'self':finished.var('Camera'),'FromAlpha':1,'ToAlpha':0,'Duration':.35,'Color':unreal.LinearColor(0,0,0,1),'bShouldFadeAudio':False,'bHoldWhenFinished':False});finished.own('SetMode',NewMode=0);commit(finished);finished.set('TransitionCommitted',False)

 # Remaining shared functions are built in the second half below.
 build_interface_and_tick(bp,fn,scene,commit)
 for _ in range(2):
  for node,pin,value in base.MATH_LITERALS:
   og.default(node,pin,value)
 return bp,save,og.compile_bp(bp,save=True)

def build_interface_and_tick(bp,fn,scene,commit):
 # Canonical interaction dispatcher remains the single entry for E/controller use.
 f=fn('Interact');f.own('UpdateTarget');valid,no=f.branch(f.valid(f.var('Target')));tail=valid
 actions=[('home.photo','OpenPhoto'),('home.letter','OpenLetter'),('npc.mother','OpenMother'),('home.workbench','UseWorkbench'),('home.calibration_component','PickupComponent'),('home.anchor','ActivateAnchor'),('past.neri','OpenNeri'),('past.healer','OpenHealer'),('past.sela','OpenSela'),('past.linen','TakeLinen'),('past.linen_tray','DeliverLinen'),('past.canvas','TakeCanvas'),('present.memorial','OpenMemorial')]
 for tag,action in actions:yes,tail=tail.branch(tail.tag(tail.var('Target'),tag));yes.own(action)
 for tag,destination,flag in [('past.clinic_fixings',1,'ClinicInspected'),('past.harbor_fixings',2,'HarborInspected')]:
  yes,tail=tail.branch(tail.tag(tail.var('Target'),tag));yes.set(flag,True);yes.own('InstallCover',Destination=destination)
 water,tail=tail.branch(tail.tag(tail.var('Target'),'past.water'));water.set('WaterTaken',True);water.notice('You take a cup of water.');commit(water)

 f=fn('UpdateTarget');f.set('Target',None);f.set('Prompt','');active,no=f.guarded_mode(0)
 loc=active.data(CAM+'GetCameraLocation',**{'self':active.var('Camera')});rot=active.data(CAM+'GetCameraRotation',**{'self':active.var('Camera')});direction=active.data(MATH+'GetForwardVector',InRot=rot);end=active.data(MATH+'Add_VectorVector',A=loc,B=active.data(MATH+'Multiply_VectorFloat',A=direction,B=900))
 trace=active.call(SYS+'LineTraceSingle',Start=loc,End=end,TraceChannel='TraceTypeQuery1',bTraceComplex=False,ActorsToIgnore=active.var('IgnoredActors'),DrawDebugType='None',bIgnoreSelf=True)
 active.set('DebugTraceStart',loc);active.set('DebugTraceEnd',end);active.set('DebugTraceHit',og.value_pin(trace,'ReturnValue'))
 hit,miss=active.branch(og.value_pin(trace,'ReturnValue'));br=hit.call(GS+'BreakHitResult',Hit=og.value_pin(trace,'OutHit'));actor=og.value_pin(br,'HitActor');hit.set('DebugHitActor',actor)
 tagged,no=hit.branch(hit.tag(actor,'Opening.Interactable'));near,no=tagged.branch(tagged.data(MATH+'LessEqual_DoubleDouble',A=tagged.data(ACT+'GetDistanceTo',**{'self':actor,'OtherActor':tagged.var('Player')}),B=tagged.var('InteractionRange')));near.set('Target',actor);tail=near
 labels={'home.photo':'F / E  Inspect photograph','home.letter':'E  Read unsent letter','npc.mother':'E  Speak with Mother','home.workbench':'E  Examine / test the secured contact','home.calibration_component':'E  Take prepared contact','home.anchor':'E  Use gate anchor','past.neri':'E  Speak with Neri','past.healer':'E  Speak with Healer','past.sela':'E  Speak with Sela','past.water':'E  Take water','past.linen':'E  Collect wrapped clinic linen','past.linen_tray':'E  Deliver clinic linen','past.canvas':'E  Take waterproof sheet and straps','present.memorial':'E  Read historical display'}
 for tag,text in labels.items():yes,tail=tail.branch(tail.tag(actor,tag));yes.set('Prompt',text)
 for tag,dest,label in [('past.clinic_fixings',1,'clinic courtyard'),('past.harbor_fixings',2,'harbor waiting shelter')]:
  yes,tail=tail.branch(tail.tag(actor,tag));committed,open_=yes.branch(gt(yes,yes.var('StormCover'),0));committed.set('Prompt','E  Inspect shelter fixings — history already committed')
  owned,inspect=open_.branch(open_.var('CanvasOwned'));planned,change=owned.branch(owned.eq(owned.var('CanvasPlan'),dest));planned.set('Prompt','E  Install canvas at '+label+' (commits choice)');change.set('Prompt','E  Plan installation at '+label);inspect.set('Prompt','E  Inspect '+label+' fixings')

 # A dialogue does not take over the player's physical or desktop head direction.
 f=fn('SetMode');f.set('Mode',f.g.input('NewMode'));f.call(CTL+'ResetIgnoreMoveInput',**{'self':f.var('Controller')});f.call(CTL+'ResetIgnoreLookInput',**{'self':f.var('Controller')})
 locked,no=f.branch(f.and_(f.not_(f.eq(f.g.input('NewMode'),0)),f.not_(f.eq(f.g.input('NewMode'),3))));locked.call(CTL+'SetIgnoreMoveInput',**{'self':locked.var('Controller'),'bNewMoveInput':True});locked.call(CTL+'SetIgnoreLookInput',**{'self':locked.var('Controller'),'bNewLookInput':True})
 intro,no=no.branch(no.and_(no.eq(no.g.input('NewMode'),3),no.var('IntroActive')));intro.call(CTL+'SetIgnoreMoveInput',**{'self':intro.var('Controller'),'bNewMoveInput':True})
 f=fn('OpenPause');f.set('PauseReturnMode',f.var('Mode'));f.own('RestorePhoto');f.set('Testing',False);f.panel(6,'Paused','1  Resume\n\n2  Save committed progress\n\n3  Load saved progress\n\nUnfinished placements, tests and transitions are not saved.','Esc / 1  Resume    2  Save    3  Load');f.call(GS+'SetGamePaused',bPaused=True)
 f=fn('CloseModal');paused,other=f.guarded_mode(6);paused.call(GS+'SetGamePaused',bPaused=False);talking,rest=paused.branch(paused.and_(paused.eq(paused.var('PauseReturnMode'),3),paused.var('DialogueActive')));talking.own('RenderDialogueLine');document,rest=rest.branch(rest.eq(rest.var('PauseReturnMode'),2));letter,mem=document.branch(eqs(document,document.var('DocumentKind'),'letter'));letter.own('ShowLetterDocument');ending,mem=mem.branch(eqs(mem,mem.var('DocumentKind'),'ending'));ending.own('EndSlice');help_,mem=mem.branch(eqs(mem,mem.var('DocumentKind'),'help'));help_.own('OpenHelp');mem.own('ShowMemorialDocument');rest.own('SetMode',NewMode=0);rest.own('RefreshUI')
 other.own('RestorePhoto');other.set('DialogueActive',False);other.set('DialogueWaitingChoice',False);other.set('DialoguePartnerActor',None);other.set('Testing',False);other.set('TestElapsed',0);other.own('SetMode',NewMode=0);other.own('RefreshUI')
 for name,index in [('HandleOne',1),('HandleTwo',2),('HandleThree',3)]:
  f=fn(name);paused,rest=f.guarded_mode(6)
  if index==1:paused.own('CloseModal')
  elif index==2:paused.own('SaveProgress');ok,no=paused.branch(paused.var('SaveSucceeded'));ok.notice('Committed progress saved.')
  else:paused.own('LoadProgress')
  dialogue,rest=rest.guarded_mode(3);dialogue.own('ChooseDialogue',ChoiceIndex=index);watch,rest=rest.guarded_mode(4);watch.own('SelectIsland',Island=index)

 f=fn('MovementFrame');jog,walk=f.branch(f.key('LeftShift',held=True))
 for flow,speed in [(jog,420),(walk,260)]:flow.set('MaxWalkSpeed',speed,flow.var('CharacterMovement',flow.var('Player'),'/Script/Engine.Character'),'/Script/Engine.CharacterMovementComponent')
 f=merge(jog,walk);toggle,no=f.branch(f.key('LeftControl'));crouched,standing=toggle.branch(toggle.var('bIsCrouched',toggle.var('Player'),'/Script/Engine.Character'));crouched.call(CHAR+'UnCrouch',**{'self':crouched.var('Player')});standing.call(CHAR+'Crouch',**{'self':standing.var('Player')})
 f=fn('InputFrame');transition,normal=f.guarded_mode(7)
 paused,normal=normal.guarded_mode(6)
 for key,action in [('Escape','CloseModal'),('One','HandleOne'),('Two','HandleTwo'),('Three','HandleThree')]:yes,paused=paused.branch(paused.key(key));yes.own(action)
 esc,normal=normal.branch(normal.key('Escape'));esc.own('OpenPause')
 dialogue,normal=normal.guarded_mode(3)
 for key,action in [('SpaceBar','SkipRecollections'),('One','HandleOne'),('Two','HandleTwo'),('Three','HandleThree'),('E','AdvanceDialogue')]:yes,dialogue=dialogue.branch(dialogue.key(key));yes.own(action)
 photo,normal=normal.guarded_mode(1)
 for key,action in [('E','CloseModal'),('F','CloseModal'),('R','FlipPhoto')]:yes,photo=photo.branch(photo.key(key));yes.own(action)
 for key,yaw in [('Left',-2.0),('Right',2.0)]:yes,photo=photo.branch(photo.key(key,held=True));yes.call(ACT+'K2_AddActorLocalRotation',**{'self':yes.var('HeldPhoto'),'DeltaRotation':unreal.Rotator(pitch=0,yaw=yaw,roll=0),'bSweep':False,'bTeleport':True})
 doc,normal=normal.guarded_mode(2);yes,doc=doc.branch(doc.key('E'));yes.own('CloseDocument')
 watch,normal=normal.guarded_mode(4)
 for key,action,params in [('Q','CloseModal',{}),('E','ConfirmWatch',{}),('MouseScrollUp','RotateDial',{'Direction':1}),('Right','RotateDial',{'Direction':1}),('MouseScrollDown','RotateDial',{'Direction':-1}),('Left','RotateDial',{'Direction':-1}),('M','MapView',{}),('P','RequestPerspective',{}),('T','RequestTimePause',{}),('One','HandleOne',{}),('Two','HandleTwo',{}),('Three','HandleThree',{}),('Four','SelectIsland',{'Island':4})]:
  yes,watch=watch.branch(watch.key(key))
  if key=='E':testing,confirm=yes.branch(yes.var('Testing'));testing.own('CloseModal');confirm.own(action,**params)
  else:yes.own(action,**params)
 journal,normal=normal.guarded_mode(5)
 for key in ['Tab','E']:yes,journal=journal.branch(journal.key(key));yes.own('CloseModal')
 for key,direction in [('Left',-1),('Right',1)]:yes,journal=journal.branch(journal.key(key));yes.own('TurnJournal',Direction=direction)
 explore,no=normal.guarded_mode(0)
 for key,action in [('F1','OpenHelp'),('Tab','OpenJournal'),('Q','OpenWatch'),('F','InspectSelected'),('E','Interact')]:yes,explore=explore.branch(explore.key(key));yes.own(action)
 explore.own('MovementFrame')
 f=fn('OpenHelp');f.set('PendingDocumentScene','');f.set('DocumentKind','help');f.panel(2,'Controls','WASD / Mouse  Move / Look\nShift  Jog     Ctrl  Crouch     Space  Jump\nE  Interact / Continue     1 / 2 / 3  Choose response\nF  Inspect selected photo or letter     R  Turn held photo\nQ  Watch     Wheel / arrows  Select era     E  Confirm\nTab  Journal     Left / Right  Page\nEsc  Pause     1 Resume / 2 Save / 3 Load\n\nDialogue waits for your input. Walking away never chooses\nan answer. The watch uses the courtyard gate anchor.','E  Close    Esc  Pause')

 f=fn('RefreshUI');past,present=f.branch(f.eq(f.var('EraIndex'),1));past.set('ContextLabel','CHAPTER 2  /  VERDANT  /  PAST');returned,opening=present.branch(present.var('HasDeparted'));returned.set('ContextLabel','CHAPTER 2  /  VERDANT  /  PRESENT');opening.set('ContextLabel','CHAPTER 1  /  VERDANT  /  PRESENT');f=merge(past,returned,opening);finished,rest=f.branch(f.var('Chapter2Complete'));finished.set('Objective','Chapters 1–2 complete. The lamp is still on.')
 present,past=rest.branch(rest.eq(rest.var('EraIndex'),0));returned,home=present.branch(present.var('HasReturned'));observed,memorial=returned.branch(returned.var('ConsequenceObserved'));observed.set('Objective','Return to Mother in the surviving room.');memorial.set('Objective','Read the historical display beside the gate.')
 tail=home
 for flag,text in [('DepartureDone','Use the gate anchor; select Verdant before the war and confirm.'),('WatchCalibrated','Meet Mother at the gate; connect the return signal.'),('ComponentPlaced','Complete both stable tests at the workbench.'),('ComponentCollected','Secure the prepared contact in the watch.'),('RepairIdentified','Take the prepared contact from its dish.'),('MotherSpoken','Finish the last contact adjustment at the workbench.')]:yes,tail=tail.branch(tail.var(flag));yes.set('Objective',wrap(text,60))
 tail.set('Objective',wrap(CONTENT['scenes']['C1_00']['documents']['objective'],60))
 tail=past
 for cond,text in [(lambda x:x.var('HealerReportDone'),'Return to the gate and confirm the present-day return signal.'),(lambda x:gt(x,x.var('StormCover'),0),'Report the installed cover to the Healer.'),(lambda x:x.var('CanvasOwned'),'Choose one site. Inspect its fixings, then install the single sheet.'),(lambda x:x.var('CanvasOffered'),'Collect the waterproof sheet from Sela’s counter.'),(lambda x:x.var('CanvasRequestKnown'),'Ask Sela about a cover for the courtyard.'),(lambda x:x.eq(x.var('LinenState'),3),'Return to the clinic; ask what else is needed.'),(lambda x:x.eq(x.var('LinenState'),2),'Place the wrapped linen in the clinic delivery tray.'),(lambda x:x.eq(x.var('LinenState'),1),'Collect Sela’s marked parcel of clinic linen.'),(lambda x:x.var('NeriMet'),'Find the clinic with blue shutters and speak with the Healer.')]:yes,tail=tail.branch(cond(tail));yes.set('Objective',text)
 tail.set('Objective','Recognize the street and speak with the local resident by the gate.')

 def append(f,text):f.set('PanelText',concat(f,f.var('PanelText'),concat(f,'\n',text) if base.vpin(text) else '\n'+wrap(text)))
 f=fn('OpenJournal');f.own('RestorePhoto');f.set('JournalPage',0);f.own('RenderJournal')
 f=fn('TurnJournal');f.set('JournalPage',f.data(MATH+'Clamp',Value=num(f,f.var('JournalPage'),f.g.input('Direction')),Min=0,Max=2));f.own('RenderJournal')
 f=fn('RenderJournal');tail=f
 pages=[('Journal — 1 / 3 — Home',[('PhotoSeen','Family photograph: Mother holds you as a baby; your father took it.'),('PhotoBackSeen','Photo inscription: Our first summer at home.'),('LetterRead','Read Mother’s unsent letter. It does not identify a recipient.'),('MotherSpoken','Spoke with Mother before the final test.'),('WatchCalibrated','Return signal stable after two contact tests.')]),('Journal — 2 / 3 — Verdant',[('NeriMet','Met Neri; discovered the clinic with blue shutters.'),('HealerMet','Met the Healer at the clinic.'),('SelaMet','Met Sela at her shop.'),('CanvasRequestKnown','One sound waterproof sheet can cover only one set of fixings.'),('ConsequenceObserved','Mother remembers the displayed record as having been here for years.')])]
 for i,(title,notes) in enumerate(pages):
  page,tail=tail.branch(tail.eq(tail.var('JournalPage'),i));page.set('PanelTitle',title);page.set('PanelText',concat(page,'CURRENT OBJECTIVE\n',page.var('Objective')))
  for flag,text in notes:yes,no=page.branch(page.var(flag));append(yes,text);page=merge(yes,no)
  page.set('PanelFooter','Left / Right  Page    Tab / E  Close    Esc  Pause');page.own('SetMode',NewMode=5)
 tail.set('PanelTitle','Journal — 3 / 3 — Observations');tail.set('PanelText','TIMELINE OBSERVATIONS')
 original,no=tail.branch(tail.var('OriginalMemorialRead'));append(original,'PRIOR OBSERVATION\n'+CONTENT['scenes']['C1_07']['documents']['plaque']);no.set('PanelText','TIMELINE OBSERVATIONS\nNo original memorial observation recorded.');tail=merge(original,no)
 done,no=tail.branch(tail.var('Chapter2Complete'));prior,other=done.branch(done.var('OriginalMemorialRead'));append(prior,CONTENT['scenes']['C2_09']['documents']['journal_prior']);append(other,CONTENT['scenes']['C2_09']['documents']['journal_otherwise']);tail=merge(prior,other,no)
 tail.set('PanelFooter','Left / Right  Page    Tab / E  Close    Esc  Pause');tail.own('SetMode',NewMode=5)
 f=fn('MapView');f.set('PanelText','DISCOVERED LOCATIONS\nHome and courtyard gate');tail=f
 for flag,text in [('NeriMet','Clinic — blue shutters along the familiar street.'),('SelaMet','Sela’s shop — across the square.'),('HarborInspected','Harbor waiting shelter — beside the lane to the water.')]:yes,no=tail.branch(tail.var(flag));append(yes,text);tail=merge(yes,no)
 tail.set('PanelTitle','Verdant — local map');tail.set('PanelFooter','Q  Close    Left / Right  Select era    E  Confirm at gate');tail.own('SetMode',NewMode=4)
 f=fn('EndSlice');f.set('DocumentKind','ending');f.set('PendingDocumentScene','');f.panel(2,'The lamp is still on','THE OTHER SIDE OF YESTERDAY\n\nChapters 1–2 complete.\n\nThe city remains damaged. One community record now exists because of the shelter you made usable.','E  Return to the surviving room    Esc  Pause');saved,failed=f.branch(f.var('SaveSucceeded'));saved.set('PanelText',concat(saved,saved.var('PanelText'),'\n\nYour progress has been saved.'));failed.set('PanelText',concat(failed,failed.var('PanelText'),'\n\nProgress is still in this session. The save could not be written.'))

 # Authored, collision-free NPC walking. Never a tracked-camera animation.
 f=fn('NpcTick')
 def walk_npc(flow,flag,animflag,ref,indexname,points,era):
  active,inactive=flow.branch(flow.and_(flow.var(flag),flow.eq(flow.var('EraIndex'),era)))
  started,start=active.branch(active.var(animflag));mesh=start.data(ACT+'GetComponentByClass',**{'self':start.var(ref),'ComponentClass':'/Script/Engine.SkeletalMeshComponent'});start.call('/Script/Engine.SkeletalMeshComponent.PlayAnimation',**{'self':mesh,'NewAnimToPlay':start.var('WalkAnimation'),'bLooping':True});start.set(animflag,True);active=merge(started,start)
  tail=active
  for i,p in enumerate(points):
   step,tail=tail.branch(tail.eq(tail.var(indexname),i));current=step.data(ACT+'K2_GetActorLocation',**{'self':step.var(ref)});target=unreal.Vector(*p);new=step.data(MATH+'VInterpTo_Constant',Current=current,Target=target,DeltaTime=step.g.input('DeltaSeconds'),InterpSpeed=100)
   step.call(ACT+'K2_SetActorLocation',**{'self':step.var(ref),'NewLocation':new,'bSweep':False,'bTeleport':False});distance=step.data(MATH+'Vector_Distance',V1=new,V2=target);arrived,moving=step.branch(step.data(MATH+'Less_DoubleDouble',A=distance,B=12));arrived.set(indexname,i+1)
  tail.set(flag,False);tail.set(animflag,False);mesh=tail.data(ACT+'GetComponentByClass',**{'self':tail.var(ref),'ComponentClass':'/Script/Engine.SkeletalMeshComponent'});tail.call('/Script/Engine.SkeletalMeshComponent.PlayAnimation',**{'self':mesh,'NewAnimToPlay':tail.var('IdleAnimation'),'bLooping':True})
  return merge(tail,inactive)
 f=walk_npc(f,'NeriMoving','NeriAnimActive','NeriActor','NeriWaypoint',[(100,500,970),(100,-120,1032),(120,-570,1077)],1)
 gate,home=f.branch(f.var('MotherToGate'))
 walk_npc(gate,'MotherMoving','MotherAnimActive','MotherActor','MotherWaypoint',[(-915,1240,1011),(-760,1240,1011),(-600,1240,1011),(-430,1240,1011),(-300,1240,966),(-150,1240,920),(-40,1240,896)],0)
 walk_npc(home,'MotherMoving','MotherAnimActive','MotherActor','MotherWaypoint',[(-430,1240,1011),(-600,1240,1011),(-760,1240,1011),(-915,1240,1011),(-915,1412,1011)],0)

 f=fn('StoryTick');f.set('LineElapsed',f.data(MATH+'Add_DoubleDouble',A=f.var('LineElapsed'),B=f.g.input('DeltaSeconds')))
 real=f.data(GS+'GetRealTimeSeconds');away,home=f.branch(f.eq(f.var('EraIndex'),1));delta=away.data(MATH+'Subtract_DoubleDouble',A=real,B=away.var('LastRealSeconds'));away.set('ReturnClockSeconds',away.data(MATH+'Add_DoubleDouble',A=away.var('ReturnClockSeconds'),B=away.data(MATH+'FMax',A=delta,B=0)));f=merge(away,home);f.set('LastRealSeconds',real)
 partner,none=f.branch(f.and_(f.var('DialogueActive'),f.valid(f.var('DialoguePartnerActor'))));far,near=partner.branch(partner.data(MATH+'Greater_DoubleDouble',A=partner.data(ACT+'GetDistanceTo',**{'self':partner.var('Player'),'OtherActor':partner.var('DialoguePartnerActor')}),B=420));far.own('CloseModal');f=merge(far,near,none)
 test,no=f.branch(f.var('Testing'));test.set('TestElapsed',test.data(MATH+'Add_DoubleDouble',A=test.var('TestElapsed'),B=test.g.input('DeltaSeconds')));done,waiting=test.branch(test.data(MATH+'GreaterEqual_DoubleDouble',A=test.var('TestElapsed'),B=test.var('CalibrationSeconds')));done.set('Testing',False);done.set('CalibrationTests',num(done,done.var('CalibrationTests'),1));commit(done)
 first,second=done.branch(done.eq(done.var('CalibrationTests'),1));scene(first,'C1_05.first_test','BenchActor');scene(second,'C1_05.second_test','BenchActor')
 # The notice clock is visual feedback only, never a narrative failure timer.
 positive,expired=no.branch(no.data(MATH+'Greater_DoubleDouble',A=no.var('NoticeRemaining'),B=0));positive.set('NoticeRemaining',positive.data(MATH+'Subtract_DoubleDouble',A=positive.var('NoticeRemaining'),B=positive.g.input('DeltaSeconds')));expired.set('Notice','')
 f=fn('CameraFraming');boom=f.data(ACT+'GetComponentByClass',**{'self':f.var('Player'),'ComponentClass':'/Script/Engine.SpringArmComponent'});valid,none=f.branch(f.valid(boom));inside,outside=valid.branch(valid.data(MATH+'IsPointInBox',Point=valid.data(ACT+'K2_GetActorLocation',**{'self':valid.var('Player')}),BoxOrigin=unreal.Vector(-820,1300,1180),BoxExtent=unreal.Vector(390,330,300)))
 for flow,target in [(inside,140),(outside,outside.var('OriginalArmLength'))]:flow.set('TargetArmLength',flow.data(MATH+'FInterpTo',Current=flow.var('TargetArmLength',boom,'/Script/Engine.SpringArmComponent'),Target=target,DeltaTime=flow.g.input('DeltaSeconds'),InterpSpeed=8),boom,'/Script/Engine.SpringArmComponent')
 f=fn('UpdateStep');routing,f=f.branch(f.var('RoutingCamera'));ready,initial=f.branch(f.valid(f.var('Player')));initial.own('Initialize');ready.own('CameraFraming',DeltaSeconds=ready.g.input('DeltaSeconds'));ready.own('InputFrame');ready.own('UpdateTarget');ready.own('StoryTick',DeltaSeconds=ready.g.input('DeltaSeconds'));ready.own('NpcTick',DeltaSeconds=ready.g.input('DeltaSeconds'));ready.own('TravelTick',DeltaSeconds=ready.g.input('DeltaSeconds'))
 # Initialization owns no extra pawn/controller and never rotates the camera.
 f=fn('Initialize');f.set('Player',f.data(GS+'GetPlayerCharacter',PlayerIndex=0));f.set('Controller',f.data(GS+'GetPlayerController',PlayerIndex=0));f.set('Camera',f.data(GS+'GetPlayerCameraManager',PlayerIndex=0));f,notready=f.branch(f.and_(f.valid(f.var('Player')),f.valid(f.var('Controller'))))
 # Stock Shipping ignores map URL overrides. Our explicit camera launch flags
 # choose an existing map before loading story progress, without replacing its pawn.
 command=f.data(SYS+'GetCommandLine')
 for flag,klass,map_name in [('-YesterdayFirstPerson','/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter.BP_FirstPersonCharacter_C','Quarter_FirstPerson'),('-YesterdayThirdPerson','/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter.BP_ThirdPersonCharacter_C','Quarter_ThirdPerson')]:
  wanted,ordinary=f.branch(f.data(SYS+'ParseParam',InString=command,InParam=flag.lstrip('-')));cast=wanted.g.cast(klass,wanted.var('Player'));og.link(wanted.cur,og.pin_in(cast));correct=Flow(wanted.g,og.pin_out(cast));redirect=Flow(wanted.g,og.pin_out(cast,'CastFailed'));redirect.set('RoutingCamera',True);redirect.call(GS+'OpenLevel',LevelName='/Game/BriefTest/Maps/'+map_name,bAbsolute=True,Options='');f=merge(correct,ordinary)
 boom=f.data(ACT+'GetComponentByClass',**{'self':f.var('Player'),'ComponentClass':'/Script/Engine.SpringArmComponent'});third,first=f.branch(f.valid(boom));third.set('OriginalArmLength',third.var('TargetArmLength',boom,'/Script/Engine.SpringArmComponent'));f=merge(third,first)
 f.call(ACT+'SetTickableWhenPaused',**{'self':f.var('Controller'),'bTickableWhenPaused':True});f.set('bShouldPerformFullTickWhenPaused',True,f.var('Controller'),'/Script/Engine.PlayerController');f.call(SYS+'ExecuteConsoleCommand',Command='DisableAllScreenMessages',SpecificPlayer=f.var('Controller'));f.call(ARR+'Array_AddUnique',TargetArray=f.var('IgnoredActors'),NewItem=f.var('Player'));f.call(PC+'ClientSetHUD',**{'self':f.var('Controller'),'NewHUDClass':'/Game/Opening/Blueprints/BP_OpeningHUD.BP_OpeningHUD_C'});f.own('LoadProgress');f.own('RefreshUI')
 f.own('CameraFraming',DeltaSeconds=1.0)

def main():
 report={'success':False,'scope':'Chapters 1–2 authored draft','source_sha256':CONTENT['source_sha256'],'gameplay_runtime':'Native Blueprints','optional_pause_and_perspective':'Unavailable; no existing authored reactive/perspective system'}
 settings=None;promotion=None
 try:
  settings=unreal.get_default_object(unreal.load_class(None,'/Script/BlueprintGraph.BlueprintEditorSettings'));promotion=settings.get_editor_property('bEnableTypePromotion');settings.set_editor_property('bEnableTypePromotion',False)
  # Reuse A's working object inspection and character controls before extending.
  base.build_actions()
  bp,save,compiled=build_story()
  from build_opening_hud import build_hud
  hud=build_hud(og.L.generated_class(bp));og.compile_bp(bp,save=True)
  from build_opening_scene import build_scene
  build_scene()
  from build_chapter2_scene import build_scene2
  world=build_scene2(og.L.generated_class(bp))
  report.update(success=True,manager=compiled,hud=hud.get_path_name(),world=world,dialogue_nodes=len(NODES))
 except Exception:report['error']=traceback.format_exc();raise
 finally:
  if settings is not None and promotion is not None:settings.set_editor_property('bEnableTypePromotion',promotion)
  (ROOT/'chapters_story_build_report.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')

if __name__=='__main__':main()
