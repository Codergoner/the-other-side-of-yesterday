"""Validate and structure the supplied Chapters 1–2 draft as authored content.

This is a pure content import, not an Unreal asset/gameplay/voice verification.
It uses only Python's standard library. No engine process is started.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import re
import shutil

PROJECT = Path(__file__).resolve().parents[1]
CONTENT = PROJECT / 'ContentData'
LEGACY_SOURCE = CONTENT / 'storysource' / 'The_Other_Side_of_Yesterday_Chapters_1_2_Dialogue.md'
MASTER_SOURCE = PROJECT.parent / 'docs' / 'TOSOY_Chapters_1_2' / 'MASTER_PROMPT.md'
DEFAULT_SOURCE = MASTER_SOURCE if MASTER_SOURCE.is_file() else LEGACY_SOURCE
EXPECTED = ['C1_%02d' % n for n in range(9)] + ['C2_00','C2_01','C2_02','C2_03','C2_04','C2_05A','C2_05B','C2_06','C2_07','C2_08A','C2_08B','C2_09']
SPEECH = re.compile(r'^\*\*(Protagonist|Mother|Healer|Sela|Neri|NPC)(?:,[^*]*)?:\*\*\s+"(.*)"\s*$')
SCENE = re.compile(r'^(#{2,3}) (C[12]_\d\d[A-B]?) — (.+)$')
HEADING = re.compile(r'^(#{1,6}) (.+)$')


def slug(text):
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def quoted(text):
    match = re.search(r'"(.*)"', text)
    return match.group(1) if match else ''


def parse(source):
    scenes = {}
    current = None
    block = 'opening'
    heading = None
    letter = []
    scene_depth = None
    all_source_speech = []
    for number, line in enumerate(source.splitlines(), 1):
        sm = SCENE.match(line)
        if sm:
            scene_id = sm.group(2)
            if scene_id in scenes:
                raise ValueError('Duplicate scene identifier %s at source line %d' % (scene_id,number))
            scene_depth = len(sm.group(1))
            current = {'id':scene_id,'title':sm.group(3),'source_heading_line':number,'blocks':{'opening':[]},'choice_definitions':{},'documents':{},'document_source_lines':{},'statuses':[],'status_source_lines':[]}
            scenes[current['id']] = current
            block = 'opening'
            heading = None
            letter = []
            continue
        hm = HEADING.match(line)
        if current is not None and hm and len(hm.group(1)) <= scene_depth:
            current = None
        speech = SPEECH.match(line)
        if speech:
            all_source_speech.append({'speaker':speech.group(1),'text':speech.group(2),'source_line':number,'scene_id':current['id'] if current else None})
        if current is None:
            continue
        if hm and len(hm.group(1)) == scene_depth + 1:
            heading = hm.group(2)
            choice = re.match(r'(?:Player )?choice ([A-Z]) — ', heading,re.IGNORECASE)
            if choice:
                block = 'choice_' + choice.group(1)
                current['choice_definitions'][choice.group(1)] = {'label':quoted(heading),'source_line':number}
            elif heading == 'Shared continuation':block = 'continuation'
            elif heading == 'Shared ending':block = 'ending'
            elif heading.startswith('Optional question'):block = 'optional_question'
            else:block = slug(heading)
            current['blocks'].setdefault(block,[])
        if speech:
            target = current['blocks'].setdefault(block,[])
            target.append({'id':current['id']+'.'+block+'.%03d'%(len(target)+1),'speaker':speech.group(1),'text':speech.group(2),'source_line':number})
        if line.startswith('>'):
            letter.append(line[1:].lstrip())
            current['documents']['letter'] = '\n'.join(letter).strip()
            current['document_source_lines'].setdefault('letter',[]).append(number)
        docs = {
            '**Writing on the back:**':'reverse', '**Plaque:**':'plaque',
            '**New caption:**':'caption', '**Journal objective:**':'objective',
            '**Journal, if original memorial inspected:**':'journal_prior',
            '**Otherwise:**':'journal_otherwise',
        }
        for prefix,key in docs.items():
            if line.startswith(prefix):
                current['documents'][key] = quoted(line)
                current['document_source_lines'][key] = [number]
        display = re.match(r'^\*\*Watch display:\*\*\s+`([^`]+)`',line)
        if display:current['statuses'].append(display.group(1));current['status_source_lines'].append(number)
        display = re.match(r'^- `([^`]+)`$',line)
        if display:current['statuses'].append(display.group(1));current['status_source_lines'].append(number)
        destination = re.match(r'^- \*\*(Clinic|Harbor|Not yet):\*\* "(.*)"$',line)
        if destination:
            key = {'Clinic':'A','Harbor':'B','Not yet':'C'}[destination.group(1)]
            current['choice_definitions'][key] = {'label':destination.group(2),'source_line':number}
        if line.startswith('**Common Sela response after selecting a destination:**'):
            current['blocks']['choice_response'] = [{'id':current['id']+'.choice_response.001','speaker':'Sela','text':quoted(line),'source_line':number}]
    return scenes,all_source_speech


def authored(scenes):
    for scene in scenes.values():
        scene['opening'] = scene['blocks'].get('opening',[])
        scene['continuation'] = scene['blocks'].get('continuation',scene['blocks'].get('ending',[]))
        scene['choices'] = {}
        scene['variants'] = {}
        scene['minimum_line_seconds'] = .75
        scene['manual_advance'] = True
        scene['completion_boundary'] = 'final_manual_advance'
        for key,definition in scene['choice_definitions'].items():
            body = copy.deepcopy(scene['blocks'].get('choice_'+key,[]))
            label = definition['label']
            if not body or body[0]['speaker']!='Protagonist' or body[0]['text']!=label:
                body.insert(0,{'id':scene['id']+'.choice_'+key+'.selected','speaker':'Protagonist','text':label,'source_line':definition['source_line'],'source_origin':'selected_choice_heading'})
            scene['choices'][key] = {'id':scene['id']+'.choice_'+key,'label':label,'lines':body,'only_on_explicit_selection':True,'next':'continuation' if scene['continuation'] else 'complete'}
    scenes['C1_00']['recollections'] = {name:scenes['C1_00']['blocks'][name] for name in ['five_years_earlier','three_years_earlier','one_year_earlier']}
    scenes['C1_00'].update(skippable=True,once=True,skip_effect={'INTRO_SEEN':True},skip_grants_unseen_clues=False)
    scenes['C1_01'].update(once=True,repeat_behavior='object_and_reverse_only',completion_effects={'PHOTO_READ':True})
    scenes['C1_02'].update(once=True,repeat_behavior='read_letter_without_exchange',completion_effects={'LETTER_READ':True},consumes_object=False)
    scenes['C1_03'].update(requires='NOT (PHOTO_READ AND LETTER_READ)',completion_effects={},departure_allowed=True,relationship_penalty=0)
    scenes['C1_04'].update(requires='PHOTO_READ AND LETTER_READ AND NOT MOTHER_DEPARTURE_TALK_DONE',completion_effects={'MOTHER_DEPARTURE_TALK_DONE':True})
    for key,value in [('A','STOP_WAR'),('B','FIND_FATHER'),('C','AFRAID')]:
        scenes['C1_04']['choices'][key].update(choice_effects={'MOTHER_OPENING_RESPONSE':value},relationship_delta=0)
    lines = scenes['C1_05']['opening']
    scenes['C1_05']['stages'] = {'identify':lines[:2],'placed':lines[2:3],'first_test':lines[3:7],'second_test':lines[7:]}
    scenes['C1_05']['opening']=scenes['C1_05']['stages']['identify']
    scenes['C1_05'].update(requires='MOTHER_DEPARTURE_TALK_DONE',completion_effects={'WATCH_CALIBRATED':True},required_successful_tests=2,item_id='WATCH_CONTACT',item_consumed_once_at='physical_contact_placement',completion_boundary='second_stable_test_and_final_manual_advance')
    scenes['C1_06'].update(optional=True,enabled=False,requires='WATCH_CALIBRATED AND WORKING_AUTHORED_TIME_REACTIVE_SYSTEM',omission_blocks_departure=False)
    scenes['C1_07'].update(optional=True,completion_effects={'ORIGINAL_MEMORIAL_READ':True},preserve_original_observation=True)
    scenes['C1_08'].update(requires='WATCH_CALIBRATED AND VALID_GATE_ANCHOR',completion_boundary='explicit_transition_confirmation_and_safe_destination_restored',confirmation_required=True)
    scenes['C2_00'].update(requires='FIRST_PAST_ARRIVAL',completion_effects={'PAST_ARRIVAL_MET_NERI':True})
    scenes['C2_01'].update(display_name='Healer',completion_effects={})
    scenes['C2_01']['choices']['A'].update(choice_effects={'LINEN_DELIVERY':'ACCEPTED'})
    scenes['C2_01']['choices']['B'].update(choice_effects={},temporary_refusal=True,relationship_delta=0)
    scenes['C2_01']['reoffer']=[scenes['C2_01']['opening'][-1]]
    scenes['C2_02'].update(requires='LINEN_DELIVERY == ACCEPTED',gives_item_once='CLINIC_LINEN',completion_effects={'LINEN_DELIVERY':'COLLECTED'})
    scenes['C2_03'].update(requires='PHYSICAL_LINEN_DELIVERY',completion_effects={'LINEN_DELIVERY':'DELIVERED'},consumes_item_once='CLINIC_LINEN',relationship_event={'id':'HEALER_LINEN_DELIVERED','character':'Healer','delta':10,'apply_once':True},completion_boundary='physical_delivery_transaction')
    scene=scenes['C2_04'];lines=scene['opening']
    optional = [line for line in lines if line['text']=='The courtyard. The waiting shelter.']
    scene['stages']={'healer_request':lines[:2],'shop':lines[2:len(lines)-len(optional)]}
    scene['opening']=scene['stages']['healer_request']
    scene['variants']['original_memorial_read']=optional
    scene['optional_variant_requires']={'original_memorial_read':'ORIGINAL_MEMORIAL_READ'}
    for key,value in [('A','CLINIC'),('B','HARBOR'),('C','NONE')]:
        choice=scene['choices'][key]
        if key!='C':choice['lines']+=copy.deepcopy(scene['blocks']['choice_response'])
        choice.update(choice_effects={'CANVAS_PLAN':value},commits_history=False,grants_item=False)
    scene.update(requires='LINEN_DELIVERY == DELIVERED',collectible_item_id='WATERPROOF_CANVAS',collection_requires='EXPLICIT_QUEST_ITEM_PICKUP',collection_effects={'CANVAS_OWNED':True},represented_fasteners=True,plan_reversible_until='STORM_COVER != NONE',completion_effects={},physical_installation_required=True)
    for sid,value in [('C2_05A','CLINIC'),('C2_05B','HARBOR')]:
        scenes[sid].update(requires='CANVAS_OWNED AND STORM_COVER == NONE AND PHYSICAL_INSTALLATION_COMPLETED',completion_effects={'CANVAS_OWNED':False,'STORM_COVER':value},consumes_item_once='WATERPROOF_CANVAS',completion_boundary='physical_installation_transaction',relationship_event={'id':'STORM_COVER_INSTALLED_'+value,'character':'Healer' if value=='CLINIC' else 'Sela','delta':10,'apply_once':True},locks_competing_installation=True)
    scene=scenes['C2_06']
    scene['variants']={'clinic':scene['blocks']['when_clinic_was_covered'],'harbor':scene['blocks']['when_harbor_was_covered']}
    scene['optional_question']=scene['blocks']['optional_question']
    scene['continuation']=scene['blocks']['shared_departure']
    scene.update(requires='STORM_COVER != NONE AND NOT HEALER_REPORT_DONE',completion_effects={'HEALER_REPORT_DONE':True})
    scenes['C2_07'].update(requires='HEALER_REPORT_DONE AND SAFE_QUEST_STATE AND VALID_GATE_ANCHOR',confirmation_required=True,completion_boundary='destination_restoration_succeeded')
    for sid,cover in [('C2_08A','CLINIC'),('C2_08B','HARBOR')]:
        scene=scenes[sid]
        scene['variants']={'original_memorial_read':scene['blocks']['when_the_original_memorial_was_inspected'],'otherwise':scene['blocks']['otherwise'][:1]}
        scene['continuation']=scene['blocks']['otherwise'][1:]
        scene.update(requires='ERA == PRESENT AND STORM_COVER == '+cover,completion_effects={'CONSEQUENCE_OBSERVED':True},preserve_original_observation=True,world_remains_damaged=True)
    scenes['C2_09'].update(requires='CONSEQUENCE_OBSERVED',completion_effects={'CHAPTER_2_COMPLETE':True},completion_boundary='explicit_final_line_advance',preserve_original_observation=True)
    return scenes


def graph_nodes(scenes):
    """Graph-ready nodes; side-effect descriptions are data, not runtime code."""
    nodes={}
    def node(name,lines,next_id=None,choices=None,effects=None):
        value={'id':name,'lines':copy.deepcopy(lines),'manual_advance':True,'minimum_line_seconds':.75}
        if next_id:value['next']=next_id
        if choices:value['choices']=choices
        if effects:value['completion_effects']=effects
        nodes[name]=value
        return value
    for sid,scene in scenes.items():
        if sid in ['C1_00','C1_05','C2_04','C2_06','C2_08A','C2_08B']:continue
        choices=[]
        for key,choice in scene['choices'].items():
            dest=sid+'.choice_'+key
            effects=choice.get('choice_effects',{})
            choices.append({'key':key,'label':choice['label'],'next':dest,'choice_effects':effects})
            node(dest,choice['lines'],sid+'.continuation' if scene['continuation'] else None,effects=scene.get('completion_effects') if not scene['continuation'] else None)
        node(sid+'.start',scene['opening'],sid+'.continuation' if scene['continuation'] and not choices else None,choices=choices or None,effects=scene.get('completion_effects') if not choices and not scene['continuation'] else None)
        if scene['continuation']:node(sid+'.continuation',scene['continuation'],effects=scene.get('completion_effects'))
    recollections=list(scenes['C1_00']['recollections'].items())
    for index,(key,lines) in enumerate(recollections):
        item=node('C1_00.'+key,lines,'C1_00.'+recollections[index+1][0] if index+1<len(recollections) else None)
        item.update(time_label={'five_years_earlier':'Five years earlier','three_years_earlier':'Three years earlier','one_year_earlier':'One year earlier'}[key],skippable=True)
    for key,lines in scenes['C1_05']['stages'].items():
        node('C1_05.'+key,lines,effects={'WATCH_CALIBRATED':True} if key=='second_test' else None)
    node('C2_04.healer_request',scenes['C2_04']['stages']['healer_request'])
    shop=node('C2_04.shop',scenes['C2_04']['stages']['shop'],'C2_04.choice')
    shop['next_if']=[{'when':'ORIGINAL_MEMORIAL_READ','next':'C2_04.memorial_callback'}]
    node('C2_04.memorial_callback',scenes['C2_04']['variants']['original_memorial_read'],'C2_04.choice')['requires']='ORIGINAL_MEMORIAL_READ'
    choices=[]
    for key,ch in scenes['C2_04']['choices'].items():
        choices.append({'key':key,'label':ch['label'],'next':'C2_04.choice_'+key,'choice_effects':ch.get('choice_effects',{})})
        node('C2_04.choice_'+key,ch['lines'])
    node('C2_04.choice',[],choices=choices)
    scene=scenes['C2_06']
    for key,lines in scene['variants'].items():node('C2_06.'+key,lines,'C2_06.optional_choice')
    node('C2_06.optional_choice',[],choices=[{'key':'A','label':'What if something worse is coming?','next':'C2_06.question'},{'key':'B','label':'I need to go home.','next':'C2_06.continuation'}])
    node('C2_06.question',scene['optional_question'],'C2_06.continuation')
    node('C2_06.continuation',scene['continuation'],effects={'HEALER_REPORT_DONE':True})
    for sid in ['C2_08A','C2_08B']:
        scene=scenes[sid]
        for key,lines in scene['variants'].items():node(sid+'.'+key,lines,sid+'.continuation')
        node(sid+'.continuation',scene['continuation'],effects={'CONSEQUENCE_OBSERVED':True})
    for sid,scene in scenes.items():
        if sid=='C1_00':scene['graph_entry']='C1_00.five_years_earlier'
        elif sid=='C1_05':scene['graph_entry']='C1_05.identify'
        elif sid=='C2_04':
            scene['graph_entry']='C2_04.healer_request';scene['shop_graph_entry']='C2_04.shop'
        elif sid=='C2_06':
            scene['graph_entry']=None
            scene['graph_entry_by_state']=[{'when':'STORM_COVER == CLINIC','node':sid+'.clinic'},{'when':'STORM_COVER == HARBOR','node':sid+'.harbor'}]
        elif sid in ['C2_08A','C2_08B']:
            scene['graph_entry']=None
            scene['graph_entry_by_state']=[{'when':'ORIGINAL_MEMORIAL_READ','node':sid+'.original_memorial_read'},{'when':'NOT ORIGINAL_MEMORIAL_READ','node':sid+'.otherwise'}]
        else:scene['graph_entry']=sid+'.start'
    return nodes


def conflicts():
    return [
        {'id':'PHOTO_COMPOSITION','existing':'Three-person sepia silhouette placeholder','source':'Mother holding the protagonist as a baby; photographer is absent','resolution':'Replace only provisional portrait art. Preserve home.photo actor ID and PhotoSeen save alias.'},
        {'id':'PHOTO_REVERSE','existing':'Home. Keep this close.','source':'Our first summer at home.','resolution':'Replace provisional inscription and readable inspection text; preserve PhotoBackSeen state.'},
        {'id':'LETTER','existing':'Calibration tutorial letter signed Mother','source':'Mother\'s unsent letter, beginning The upstairs room still leaks','resolution':'Replace provisional reading content; keep home.letter actor and LetterRead alias.'},
        {'id':'MOTHER_CHOICES','existing':'Repeated topic/help/goodbye tutorial','source':'Three honest opening responses and shared return-signal conversation','resolution':'Replace provisional copy; retain MotherSpoken as MOTHER_DEPARTURE_TALK_DONE alias and add persisted response.'},
        {'id':'CONTACT_REPAIR','existing':'Alignment collar in a lidded parts box; one final test','source':'Prepared contact in a dish; placement, close housing, two stable tests','resolution':'Reuse repair interaction and existing component actor ID; migrate old completed calibration without removing earned progress.'},
        {'id':'ANCHOR','existing':'Porch anchor registration only','source':'Courtyard gate return signal and explicit past/present confirmation','resolution':'Reuse anchor identifier and safe-location recovery; do not alter old save slot.'},
        {'id':'CHAPTER_2_QUEST','existing':'No implemented Chapter 2; older task mentioned provisional medicine supplies','source':'Linen delivery, one waterproof canvas, physical clinic or harbor installation, bounded archive consequence','resolution':'Use this supplied content; plan is reversible, installation commits history exactly once.'},
        {'id':'PERSPECTIVE_AND_PAUSE','existing':'No working perspective or reactive time-pause system','source':'Perspective remains locked; pause test optional only with a working system','resolution':'Do not force 100 trust or enable an unimplemented optional feature. Omission must not block departure.'},
    ]


def content_delta(scenes,raw,source_path):
    """Compare authored facts while ignoring changed Markdown line numbers."""
    previous_raw=LEGACY_SOURCE.read_bytes() if LEGACY_SOURCE.is_file() else None
    previous=parse(previous_raw.decode('utf-8-sig'))[0] if previous_raw else {}
    before={line['id']:line for scene in previous.values() for block in scene['blocks'].values() for line in block}
    after={line['id']:line for scene in scenes.values() for block in scene['blocks'].values() for line in block}
    changes=[]
    for key in sorted(set(before)|set(after)):
        old=before.get(key);new=after.get(key)
        if old is None or new is None or (old['speaker'],old['text']) != (new['speaker'],new['text']):
            changes.append({'line_id':key,'speaker':new['speaker'] if new else old['speaker'],
                'previous_text':old['text'] if old else None,'text':new['text'] if new else None,
                'previous_source_line':old['source_line'] if old else None,'source_line':new['source_line'] if new else None})
    other=[]
    for sid in sorted(set(previous)|set(scenes)):
        old=previous.get(sid);new=scenes.get(sid)
        if not old or not new:other.append({'scene':sid,'change':'Scene added or removed'});continue
        for field in ['documents','statuses']:
            if old[field]!=new[field]:other.append({'scene':sid,'field':field,'previous':old[field],'value':new[field]})
        choice_labels=lambda value:{key:ch['label'] for key,ch in value['choice_definitions'].items()}
        if choice_labels(old)!=choice_labels(new):other.append({'scene':sid,'field':'choice_labels','previous':choice_labels(old),'value':choice_labels(new)})
    return {'scope':'Authored content comparison; no Unreal runtime assertion',
        'authoritative_source':str(source_path.resolve()),'authoritative_sha256':hashlib.sha256(raw).hexdigest(),
        'preceding_source_file':'storysource/'+LEGACY_SOURCE.name,
        'preceding_source_sha256':hashlib.sha256(previous_raw).hexdigest() if previous_raw else None,
        'preceding_source_preserved':True,'spoken_changes':changes,'other_authored_changes':other,
        'heading_compatibility':'Legacy scene/branch depths 2/3 and master depths 3/4 are both supported without changing source line numbers.'}


def write_json(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    temporary.replace(path)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=DEFAULT_SOURCE);args=parser.parse_args()
    raw=args.source.read_bytes();source=raw.decode('utf-8-sig')
    # Parse and validate entirely in memory. A rejected input must not replace
    # either the preceding full source or the last valid runtime data.
    scenes,original=parse(source)
    if set(scenes)!=set(EXPECTED):
        raise SystemExit('Rejected source before writing files: scene identifier mismatch; found '+', '.join(scenes))
    delta=content_delta(scenes,raw,args.source)
    is_master='# PART II — COMPLETE AUTHORED DIALOGUE' in source
    source_copy=CONTENT/'storysource'/('MASTER_PROMPT.md' if is_master else args.source.name)
    source_sections=[i for i,line in enumerate(source.splitlines(),1) if line.startswith('# PART II —') or line.startswith('# PART III —')]
    provenance={'source_kind':'master_brief_part_ii' if is_master else 'preceding_dialogue_draft',
        'authoritative_path':str(args.source.resolve()),'full_source_sha256':hashlib.sha256(raw).hexdigest(),
        'source_line_numbers':'One-based lines in the full, byte-identical source document; no heading normalization copy.',
        'dialogue_section_start_line':source_sections[0] if source_sections else None,
        'dialogue_section_end_line':source_sections[1]-1 if len(source_sections)>1 else None,
        'preceding_source_file':delta['preceding_source_file'],'preceding_source_sha256':delta['preceding_source_sha256']}
    scenes=authored(scenes)
    data={'schema_version':1,'title':'The Other Side of Yesterday','content_status':'Development specification supplied by user' if is_master else 'Proposed production draft supplied by user','source_file':'storysource/'+source_copy.name,'source_sha256':hashlib.sha256(raw).hexdigest(),'source_provenance':provenance,'verification_scope':'Structured written content only; not an Unreal import, gameplay, voice, animation or packaged-build test.','presentation':{'manual_advance':True,'minimum_line_seconds':.75,'stage_directions_are_subtitles':False,'voice_required':False,'live_generated_dialogue':False},'save_aliases':{'PHOTO_READ':'PhotoSeen','LETTER_READ':'LetterRead','MOTHER_DEPARTURE_TALK_DONE':'MotherSpoken','WATCH_CALIBRATED':'WatchCalibrated'},'scenes':scenes,'nodes':graph_nodes(scenes),'locked_statuses':{'perspective':'PERSPECTIVE UNAVAILABLE — RELATIONSHIP NOT YET READY'},'optional_repeat_lines':{'Mother':"The lamp will be here when you get back.",'Healer_linen':"Sela's parcel should be wrapped and ready.",'Sela_canvas':'You have the only sound sheet. Check the fixings before you settle on a place.','Healer_exhausted':"I should get back to work. You're welcome to the water."},'future_perspective':{'enabled':False,'requires':['TRUST == 100','EXPLICIT_CONSENT','SPECIFIC_AUTHORED_VIEW_EXISTS'],'maximum_seconds':30,'lines':[{'speaker':'Protagonist','text':"The watch might let me see what you're seeing. Only for a few seconds."},{'speaker':'NPC','text':"You'd have to ask me first."},{'speaker':'Protagonist','text':"That's what I'm doing. You can stop it."},{'speaker':'NPC','text':'All right. Just this once.'}]}}
    failures=[]
    if set(scenes)!=set(EXPECTED):failures.append('Scene identifier mismatch')
    text=json.dumps(data,ensure_ascii=False)
    if 'Elias' in text:failures.append('Writer-only identity in playable content')
    count=0
    for scene in scenes.values():
        for block in scene['blocks'].values():
            for line in block:
                count+=1
                if ('"'+line['text']+'"') not in source:failures.append('Non-authored spoken line: '+line['id'])
                if '*[' in line['text'] or ']*' in line['text']:failures.append('Stage direction in spoken line: '+line['id'])
                if line['speaker'] not in ['Protagonist','Mother','Healer','Sela','Neri','NPC']:failures.append('Invalid speaker')
        for choice in scene['choices'].values():
            if not choice['only_on_explicit_selection']:failures.append('Choice can speak unselected')
            if ('"'+choice['label']+'"') not in source:failures.append('Non-authored choice label')
    for node in data['nodes'].values():
        links=[node['next']] if node.get('next') else []
        links += [choice['next'] for choice in node.get('choices',[])]
        links += [rule['next'] for rule in node.get('next_if',[])]
        for link in links:
            if link not in data['nodes']:failures.append('Broken node reference: '+link)
    expected_choices={'C1_04':['A','B','C'],'C1_08':['A','B'],'C2_00':['A','B'],'C2_01':['A','B'],'C2_04':['A','B','C'],'C2_09':['A','B','C']}
    choice_gate_checks=[]
    for sid,keys in expected_choices.items():
        actual=list(scenes[sid]['choices'])
        passed=actual==keys
        choice_gate_checks.append({'scene':sid,'expected_keys':keys,'actual_keys':actual,'passed':passed})
        if not passed:failures.append('Missing authored choice gates: '+sid)
        for key in keys:
            if key not in scenes[sid]['choices']:continue
            choice=scenes[sid]['choices'][key]
            if choice['lines'][0]['speaker']!='Protagonist' or choice['lines'][0]['text']!=choice['label']:failures.append('Selected protagonist response is not first: '+choice['id'])
    if 'CANVAS_OWNED' in scenes['C2_04']['choices']['C'].get('choice_effects',{}) or scenes['C2_04']['choices']['C'].get('grants_item'):failures.append('Not-yet choice grants canvas')
    if any('STORM_COVER' in ch.get('choice_effects',{}) for ch in scenes['C2_04']['choices'].values()):failures.append('Planning commits history')
    if data['nodes']['C2_09.continuation'].get('completion_effects',{}).get('CHAPTER_2_COMPLETE') is not True:failures.append('Final shared ending does not complete chapter')
    if any(data['nodes']['C2_09.choice_'+key].get('completion_effects',{}).get('CHAPTER_2_COMPLETE') for key in ['A','B','C']):failures.append('Chapter completes before the shared ending')
    expected_core_lines={line['source_line'] for line in original if line.get('scene_id')}
    actual_core_lines={line['source_line'] for scene in scenes.values() for block in scene['blocks'].values() for line in block}
    omitted=sorted(expected_core_lines-actual_core_lines)
    if omitted:failures.append('Source dialogue lines omitted: '+str(omitted))
    if count!=190:failures.append('Unexpected authored block line count: '+str(count))
    if len(data['nodes'])!=55:failures.append('Unexpected graph node count: '+str(len(data['nodes'])))
    if is_master:
        expected_change={'line_id':'C1_03.opening.001','speaker':'Mother',
            'previous_text':"You're very quiet this morning.",'text':"You're very quiet today."}
        if len(delta['spoken_changes'])!=1 or any(delta['spoken_changes'][0].get(key)!=value for key,value in expected_change.items()):
            failures.append('Master dialogue differs from the preceding source beyond its one approved early-Mother edit')
        if delta['other_authored_changes']:failures.append('Master changes authored documents, watch statuses or choice labels')
    locked_checks=[]
    for name,passed in [
        ('Future perspective remains disabled',data['future_perspective']['enabled'] is False),
        ('Future perspective requires real trust, consent and a specific authored view',data['future_perspective']['requires']==['TRUST == 100','EXPLICIT_CONSENT','SPECIFIC_AUTHORED_VIEW_EXISTS']),
        ('Future perspective remains bounded to thirty seconds',data['future_perspective']['maximum_seconds']<=30),
        ('Absent optional local pause cannot block departure',scenes['C1_06']['enabled'] is False and scenes['C1_06']['omission_blocks_departure'] is False),
    ]:
        locked_checks.append({'name':name,'passed':passed})
        if not passed:failures.append(name)
    for value in list(data['optional_repeat_lines'].values())+[line['text'] for line in data['future_perspective']['lines']]:
        if ('"'+value+'"') not in source:failures.append('Non-authored repeat or future consent line')
    routes=[]
    for cover,sid in [('CLINIC','C2_08A'),('HARBOR','C2_08B')]:
        for prior in [False,True]:
            scene=scenes[sid];variant='original_memorial_read' if prior else 'otherwise'
            routes.append({'storm_cover':cover,'original_memorial_read':prior,'first_line':scene['variants'][variant][0]['text'],'caption':scene['documents']['caption'],'journal':scenes['C2_09']['documents']['journal_prior' if prior else 'journal_otherwise'],'observed_change_effect':'CONSEQUENCE_OBSERVED','chapter_completion_effect':'CHAPTER_2_COMPLETE'})
    if failures:
        print(json.dumps({'success':False,'files_written':False,'failures':failures},indent=2))
        raise SystemExit(1)
    # Commit only a validated import. Keep the preceding full source and its
    # historical conflict report, and archive an older master copy if needed.
    source_copy.parent.mkdir(parents=True,exist_ok=True)
    if source_copy.is_file() and source_copy.read_bytes()!=raw:
        old_digest=hashlib.sha256(source_copy.read_bytes()).hexdigest()[:12]
        archive=source_copy.with_name(source_copy.stem+'.prior-'+old_digest+source_copy.suffix)
        if not archive.exists():shutil.copy2(source_copy,archive)
    if not source_copy.is_file() or source_copy.read_bytes()!=raw:
        temporary=source_copy.with_suffix(source_copy.suffix+'.tmp')
        temporary.write_bytes(raw);temporary.replace(source_copy)
    write_json(CONTENT/'chapters_1_2_dialogue.json',data)
    if not (CONTENT/'dialogue_continuity_conflicts.json').exists():
        write_json(CONTENT/'dialogue_continuity_conflicts.json',{'status':'Historical conflicts from the preceding provisional opening.','preserve':['Yesterday_Opening_v1','BP_OpeningActions','BP_OpeningHUD','BP_OpeningSave','home.photo','home.letter','home.calibration_component','home.anchor','House_FirstPerson','House_ThirdPerson'],'conflicts':conflicts()})
    report={'success':True,'scope':'Written content import/validation only','source_sha256':data['source_sha256'],'source_file':data['source_file'],'source_provenance':provenance,'source_copy_byte_identical':source_copy.read_bytes()==raw,'preceding_source_preserved':not LEGACY_SOURCE.exists() or hashlib.sha256(LEGACY_SOURCE.read_bytes()).hexdigest()==delta['preceding_source_sha256'],'scene_count':len(scenes),'spoken_block_line_count':count,'graph_node_count':len(data['nodes']),'source_dialogue_complete':not omitted,'missing_source_line_numbers':omitted,'choice_gate_checks':choice_gate_checks,'locked_feature_checks':locked_checks,'failures':failures,'consequence_route_snapshots':routes,'gameplay_tested':False,'packaged_build_tested':False,'voice_recorded':False,'animation_authored':False}
    write_json(CONTENT/'dialogue_content_validation.json',report)
    write_json(CONTENT/'master_dialogue_delta.json',delta)
    print(json.dumps({key:report[key] for key in ['success','scene_count','spoken_block_line_count','graph_node_count','failures']},indent=2))


if __name__=='__main__':main()
