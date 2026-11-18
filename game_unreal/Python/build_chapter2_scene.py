"""Author the compact Verdant chapter route into the existing Home levels.

This is editor-time scene authoring, not a second quest or dialogue runtime.
BP_OpeningActions owns every era/quest/outcome decision. NPCs and small props
reuse the existing project assets and are explicitly temporary presentation.
Import this module and call build_scene2() after compiling its manager fields.
Do not execute it concurrently with any other asset-writing Unreal process.
"""
from pathlib import Path
import json
import math
import unreal
import build_opening_scene as base

PROJECT=Path(unreal.Paths.project_dir()).resolve()
ACTORS=base.ACTORS
LEVELS=base.LEVELS
MAPS=base.MAPS
OWNED='Opening.Chapter2SceneOwned'


def floor_z(y):
    """Existing promenade collision top in Unreal centimetres."""
    return 1020.0-float(y)*.1


def house_local(world):
    x,y,z=world
    return ((1300.0-y)/100.0,(-800.0-x)/100.0,(z-896.0)/100.0)


def add_tags(actor,*extra):
    tags=[str(t) for t in actor.get_editor_property('tags')]
    for tag in (OWNED,)+tuple(extra):
        if tag and tag not in tags:tags.append(tag)
    actor.set_editor_property('tags',[unreal.Name(t) for t in tags])
    actor.set_folder_path('Opening/Chapter 2')
    return actor


def box(stable_id,label,world,dimensions,mat,shape='Cube',interactive=False,
        variant='Opening.PastOnly',blocking=False,movable=False,rotation=None):
    actor=base.mesh_actor(stable_id,label,house_local(world),dimensions,mat,
                          shape,interactive,movable,blocking,rotation)
    add_tags(actor,variant,'Opening.Blocking' if blocking else None,
             None if interactive or blocking else 'Opening.Decorative')
    if variant in ['Opening.ClinicCover','Opening.HarborCover']:add_tags(actor,'Opening.PastOnly')
    if variant in ['Opening.ClinicRecord','Opening.HarborRecord']:add_tags(actor,'Opening.PresentOnly')
    # The default playable era is present. Runtime state, not editor visibility,
    # is authoritative after a save is loaded or an anchor transition completes.
    conditional=variant in ['Opening.PastOnly','Opening.ClinicCover','Opening.HarborCover',
                            'Opening.ClinicRecord','Opening.HarborRecord']
    actor.set_actor_hidden_in_game(conditional)
    actor.set_actor_enable_collision(bool(not conditional and (interactive or blocking)))
    return actor


def beam(stable_id,label,a,b,mat,width=.12,depth=.12,variant='Opening.PastOnly',blocking=False):
    aa,bb=unreal.Vector(*a),unreal.Vector(*b)
    midpoint=tuple((a[i]+b[i])*.5 for i in range(3))
    rotation=unreal.MathLibrary.find_look_at_rotation(aa,bb)
    return box(stable_id,label,midpoint,((bb-aa).length()/100,width,depth),mat,
               variant=variant,blocking=blocking,rotation=rotation)


def marker(stable_id,label,world,variant=None):
    actor=base.owned_actor(stable_id,unreal.TargetPoint,label,house_local(world))
    add_tags(actor,variant,'Opening.Decorative')
    actor.set_actor_enable_collision(False)
    actor.set_actor_hidden_in_game(True)
    return actor


def npc(stable_id,label,world,mesh_path,scale=1.0,yaw=180):
    actor=base.owned_actor(stable_id,unreal.SkeletalMeshActor,label,house_local(world),
                           unreal.Rotator(pitch=0,yaw=yaw,roll=0),interactive=True)
    add_tags(actor,'Opening.PastOnly')
    component=actor.get_component_by_class(unreal.SkeletalMeshComponent)
    component.set_mobility(unreal.ComponentMobility.MOVABLE)
    mesh=unreal.load_asset(mesh_path)
    idle=unreal.load_asset('/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle')
    if not mesh or not idle:raise RuntimeError('Existing compatible NPC presentation assets missing')
    component.set_skeletal_mesh_asset(mesh)
    component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    component.play_animation(idle,True)
    component.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
    component.set_collision_response_to_all_channels(unreal.CollisionResponseType.ECR_IGNORE)
    component.set_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY,
                                               unreal.CollisionResponseType.ECR_BLOCK)
    actor.set_actor_scale3d(unreal.Vector(scale,scale,scale))
    actor.set_actor_hidden_in_game(True)
    actor.set_actor_enable_collision(False)
    return actor


def archive_textures():
    folder=PROJECT.parent/'output/opening/textures'
    folder.mkdir(parents=True,exist_ok=True)
    results=[]
    for kind,color in [('ClinicRegister',(213,197,159)),('HarborDeparture',(202,191,159))]:
        w,h=512,768
        pixels=bytearray(color)*(w*h)
        def rect(x0,y0,x1,y1,tint):
            for yy in range(max(0,y0),min(h,y1)):
                for xx in range(max(0,x0),min(w,x1)):
                    i=(yy*w+xx)*3;pixels[i:i+3]=bytes(tint)
        rect(18,18,w-18,h-18,(229,216,182))
        rect(55,62,w-55,71,(101,93,72))
        rect(55,91,w-150,96,(130,120,95))
        for row in range(17):
            yy=145+row*30
            rect(47,yy,w-47,yy+1,(153,145,118))
            rect(65,yy+9,180+(row*31)%78,yy+12,(116,108,84))
            rect(280,yy+9,390+(row*13)%39,yy+12,(116,108,84))
        rect(252,131,253,662,(161,151,125))
        # No names, signatures, private writer identities, or invented lists are
        # baked into this temporary art. The authored caption is readable UI.
        for yy in range(h):
            for xx in range(w):
                i=(yy*w+xx)*3;d=((xx*7+yy*11)%7)-3
                pixels[i:i+3]=bytes(max(0,min(255,c+d)) for c in pixels[i:i+3])
        path=folder/('T_'+kind+'_Provisional.png')
        base.png(path,w,h,pixels);results.append(base.texture(path))
    return results


def build_memorial(mats,register,departure):
    """Two empty mounts at the existing porch gate; each result is independent."""
    box('Opening.Gate.PostA','Opening - Courtyard gate post',(-220,1050,1130),(.18,.18,2.38),mats['wood'],variant=None,blocking=True)
    box('Opening.Gate.PostB','Opening - Courtyard gate post',(-220,1435,1130),(.18,.18,2.38),mats['wood'],variant=None,blocking=True)
    box('Opening.Gate.Header','Opening - Repaired courtyard gate lintel',(-220,1242.5,1252),(.20,4.06,.20),mats['wood'],variant=None)
    for yy in [1385,1535]:
        box('Opening.ArchiveLeg.'+str(yy),'Opening - Historical display support',(-350,yy,1068),(.12,.12,1.14),mats['wood'],variant='Opening.PresentOnly')
    memorial=box('present.memorial','Opening - Historical display',(-350,1460,1160),(.065,1.78,1.08),mats['wood'],interactive=True,variant='Opening.PresentOnly',movable=True)
    for index,yy in enumerate([1419,1501]):
        box('Opening.ArchiveRecess.'+str(index),'Opening - Empty archival mount',(-345.5,yy,1164),(.025,.71,.83),mats['dark'],variant='Opening.PresentOnly')
        for side,zz in [('Top',1208),('Bottom',1120)]:
            box('Opening.ArchiveFrame.'+str(index)+side,'Opening - Archival mount frame',(-343.5,yy,zz),(.035,.78,.045),mats['brass'],variant='Opening.PresentOnly')
        for side,y2 in [('Left',yy-38),('Right',yy+38)]:
            box('Opening.ArchiveFrame.'+str(index)+side,'Opening - Archival mount frame',(-343.5,y2,1164),(.035,.045,.85),mats['brass'],variant='Opening.PresentOnly')
    clinic=box('Opening.ClinicRecordPage','Opening - Preserved clinic register page',(-341.5,1419,1164),(.012,.63,.73),register,variant='Opening.ClinicRecord',movable=True)
    harbor=box('Opening.HarborRecordPage','Opening - Preserved departure page',(-341.5,1501,1164),(.012,.63,.73),departure,variant='Opening.HarborRecord',movable=True)
    box('Opening.ArchiveCaption','Opening - Weathered plaque strip',(-343,1460,1117),(.025,1.56,.055),mats['stone'],variant='Opening.PresentOnly')
    return memorial,clinic,harbor


def build_clinic(mats):
    y=550.0;z=floor_z(y)
    # A compact blue-shuttered room at the neighborhood edge. The broad open
    # front and level courtyard need neither jumping nor a climbing animation.
    box('Opening.ClinicPlatform','Opening - Clinic threshold',(-435,y,z-4),(2.42,2.9,.18),mats['stone'],blocking=True)
    box('Opening.ClinicRear','Opening - Clinic plaster back wall',(-555,y,z+132),(.14,2.95,2.72),mats['plaster'])
    for suffix,yy in [('North',400),('South',700)]:
        box('Opening.ClinicWall'+suffix,'Opening - Clinic side wall',(-445,yy,z+132),(2.3,.14,2.72),mats['plaster'])
        box('Opening.ClinicBlueShutter'+suffix,'Opening - Clinic blue shutter',(-320,yy,z+140),(.08,.53,1.15),mats['blue'])
    for yy in [427,673]:
        box('Opening.ClinicDoorJamb.'+str(yy),'Opening - Open clinic doorway',(-322,yy,z+126),(.18,.16,2.5),mats['wood'])
    box('Opening.ClinicDoorLintel','Opening - Open clinic doorway',(-322,y,z+253),(.2,2.62,.16),mats['wood'])
    box('Opening.ClinicRoof','Opening - Clinic tile roof',(-445,y,z+278),(2.85,3.40,.15),mats['roof'])
    # The courtyard awning frame is exposed until the canvas is installed.
    for suffix,xx,yy in [('A',-280,390),('B',-90,390),('C',-280,620),('D',-90,620)]:
        zz=floor_z(yy)
        box('Opening.ClinicAwningPost'+suffix,'Opening - Courtyard awning post',(xx,yy,zz+122),(.10,.10,2.44),mats['wood'],blocking=True)
    for yy in [390,620]:
        beam('Opening.ClinicAwningRail.'+str(yy),'Opening - Courtyard awning rail',(-280,yy,floor_z(yy)+242),(-90,yy,floor_z(yy)+242),mats['wood'],.10,.10)
    cover=box('Opening.ClinicInstalledCanvas','Opening - Installed clinic courtyard canvas',(-185,505,floor_z(505)+249),(2.05,2.46,.055),mats['canvas'],variant='Opening.ClinicCover',movable=True)
    box('Opening.ClinicTable','Opening - Clinic courtyard table',(-220,525,floor_z(525)+89),(.65,1.12,.10),mats['wood'])
    for yy in [480,570]:
        box('Opening.ClinicTableLeg.'+str(yy),'Opening - Clinic table leg',(-230,yy,floor_z(yy)+44),(.09,.09,.88),mats['wood'])
    tray=box('past.linen_tray','Opening - Clinic linen delivery tray',(-210,520,floor_z(520)+100),(.48,.50,.08),mats['brass'],interactive=True,movable=True)
    box('Opening.ClinicWaterTable','Opening - Clinic water table',(-220,650,floor_z(650)+89),(.70,.62,.10),mats['wood'])
    box('Opening.ClinicWaterJug','Opening - Clinic water jug',(-226,660,floor_z(660)+112),(.19,.19,.34),mats['clay'],'Cylinder')
    water=box('past.water','Opening - Clinic drinking cup',(-210,640,floor_z(640)+104),(.13,.13,.17),mats['clay'],'Cylinder',interactive=True,movable=True)
    install=box('past.clinic_fixings','Opening - Clinic awning fixing',(-190,390,floor_z(390)+119),(.15,.18,.22),mats['brass'],interactive=True,movable=True)
    beam('Opening.ClinicFixingStrap','Opening - Clinic repair strap',(-190,390,floor_z(390)+119),(-190,390,floor_z(390)+242),mats['canvas'],.03,.03)
    healer=npc('past.healer','Opening - Healer',(-200,580,floor_z(580)),
               '/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple',1.0,180)
    return healer,water,tray,install,cover


def build_shop_and_harbor(mats):
    # Sela stays beside the shop, in view of the shelter; no actor is visibly
    # teleported in to deliver the harbor installation dialogue.
    for yy in [-190,-415]:
        zz=floor_z(yy)
        box('Opening.ShopPost.'+str(yy),'Opening - Store canvas support',(275,yy,zz+120),(.10,.10,2.4),mats['wood'],blocking=True)
    box('Opening.ShopShade','Opening - Store shade',(220,-300,floor_z(-300)+249),(1.48,2.56,.04),mats['canvas'])
    box('Opening.ShopCounter','Opening - Storekeeper counter',(233,-300,floor_z(-300)+90),(.78,2.10,.12),mats['wood'],blocking=True)
    linen=box('past.linen','Opening - Wrapped clinic linen',(220,-235,floor_z(-300)+107),(.39,.45,.21),mats['linen'],interactive=True,movable=True)
    box('Opening.LinenWrapBand','Opening - Linen parcel wrap',(220,-235,floor_z(-300)+118),(.40,.10,.018),mats['blue'])
    canvas=box('past.canvas','Opening - Reinforced waterproof canvas',(220,-365,floor_z(-300)+106),(.42,.47,.18),mats['canvas'],interactive=True,movable=True)
    box('Opening.CanvasFasteners','Opening - Supplied repair straps',(232,-362,floor_z(-300)+116),(.08,.36,.035),mats['brass'])
    sela=npc('past.sela','Opening - Sela',(150,-300,floor_z(-300)),
             '/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple',1.0,180)
    for suffix,xx,yy in [('A',100,-525),('B',280,-525),('C',100,-775),('D',280,-775)]:
        zz=floor_z(yy)
        box('Opening.HarborShelterPost'+suffix,'Opening - Harbor waiting shelter post',(xx,yy,zz+122),(.11,.11,2.44),mats['wood'],blocking=True)
    for yy in [-525,-775]:
        beam('Opening.HarborShelterRail.'+str(yy),'Opening - Harbor waiting shelter rail',(95,yy,floor_z(yy)+244),(285,yy,floor_z(yy)+244),mats['wood'],.12,.12)
    cover=box('Opening.HarborInstalledCanvas','Opening - Installed harbor waiting cover',(190,-650,floor_z(-650)+251),(2.0,2.67,.055),mats['canvas'],variant='Opening.HarborCover',movable=True)
    box('Opening.HarborWaitingBench','Opening - Harbor waiting bench',(242,-660,floor_z(-660)+48),(.43,1.80,.10),mats['wood'],blocking=True)
    box('Opening.HarborClerkTable','Opening - Departure clerk table',(215,-560,floor_z(-560)+90),(.60,.66,.10),mats['wood'])
    install=box('past.harbor_fixings','Opening - Harbor shelter fixing',(90,-535,floor_z(-535)+116),(.18,.18,.25),mats['brass'],interactive=True,movable=True)
    destination=marker('Opening.NeriHarborDestination','Opening - Neri harbor route endpoint',(115,-610,floor_z(-610)))
    return sela,linen,canvas,install,cover,destination


def build_past_roof_patches(mats):
    # Past family interior is outside this slice; keep the same doorway and
    # close it physically in the past rather than exposing an empty family room.
    box('Opening.PastHomeDoor','Opening - Past family home closed door',(-444,1240,1123),(.14,1.14,2.24),mats['wood'],blocking=True)
    # Infill only the house's exposed wing; the original present model remains.
    # This geometry is an era presentation, never a canvas-choice consequence.
    roof_a=base.placed((1.85,-.45,7.38));roof_b=base.placed((5.85,-.45,6.0))
    beam('Opening.PastHomeWingRoof','Opening - Past intact family roof',
         (roof_a.x,roof_a.y,roof_a.z),(roof_b.x,roof_b.y,roof_b.z),mats['roof'],7.18,.14)
    for i,(x0,x1,z0,z1) in enumerate([(2.6,3.24,1.15,4.22),(4.45,5.35,1.15,4.22),
                                     (3.24,4.45,1.15,1.61),(3.24,4.45,3.37,4.22),
                                     (2.40,5.35,4.22,6.25)]):
        p=base.placed(((x0+x1)/2,-3.61,(z0+z1)/2))
        box('Opening.PastHomeWingWall.'+str(i),'Opening - Past intact family plaster',
            (p.x,p.y,p.z),(.17,x1-x0,z1-z0),mats['plaster'])
    # The next two houses along the compact street receive complete roof caps.
    for suffix,cy,z,h in [('B',2,10.4,14),('C',18,12.0,11)]:
        for side,x in [('Rear',-10.55),('Front',-3.45)]:
            a=(x*100,-cy*100,(z+h+.75)*100)
            b=(-700,-cy*100,(z+h+2.75)*100)
            beam('Opening.PastRoof'+suffix+side,'Opening - Past intact neighborhood roof',a,b,mats['roof'],11.0,.14)


def build_scene2(manager_class=None):
    """Add/reuse scene actors; the caller dispatches this in its write process."""
    animations={
        'WalkAnimation':unreal.load_asset('/Game/Characters/Mannequins/Anims/Unarmed/Walk/MF_Unarmed_Walk_Fwd'),
        'IdleAnimation':unreal.load_asset('/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle'),
    }
    if any(value is None for value in animations.values()):
        raise RuntimeError('Existing unarmed NPC walk/idle animation assets unavailable')
    register_texture,departure_texture=archive_textures()
    mats={key:unreal.load_asset(path) for key,path in {
        'wood':'/Game/Harbor/Materials/M_Wood','stone':'/Game/Harbor/Materials/M_Stone',
        'plaster':'/Game/Harbor/Materials/M_Plaster','roof':'/Game/Harbor/Materials/M_Roof',
        'clay':'/Game/Harbor/Materials/M_Terracotta','blue':'/Game/Home/Materials/M_HomeTeal',
        'canvas':'/Game/Harbor/Materials/M_Fabric','linen':'/Game/Home/Materials/M_HomeLinen',
        'brass':'/Game/Opening/Materials/M_OpeningRepairedBrass','dark':'/Game/Opening/Materials/M_OpeningInk',
    }.items()}
    if any(value is None for value in mats.values()):
        raise RuntimeError('Build existing Home/Opening materials before chapter 2 scene: '+str([k for k,v in mats.items() if v is None]))
    register_mat=base.material('M_OpeningClinicRegister',image=register_texture)
    departure_mat=base.material('M_OpeningHarborDeparture',image=departure_texture)
    report={'success':False,'scope':'Existing Home maps; era presentation and bounded archive outcomes',
            'runtime_state_owner':'BP_OpeningActions','maps':[],'warnings':[],
            'temporary_presentation':['NPCs reuse Epic mannequin meshes and unarmed idle; no voice/lip-sync is claimed.',
                'Archive pages use original paper/row placeholder art without invented names or private signatures.',
                'Clinic, shop, covers and restored roofs use existing materials and engine primitive stand-ins.']}
    for map_path in MAPS:
        if not LEVELS.load_level(map_path):raise RuntimeError('Cannot open existing Home level '+map_path)
        manager=next((a for a in ACTORS.get_all_level_actors() if a.actor_has_tag('Opening.Manager')),None)
        if manager is None:raise RuntimeError('Build the existing opening manager before chapter 2 scene')
        # New Game follows the recollections into a usable surviving room.
        # Save/load and anchor travel have their separate stable gate location.
        for start in ACTORS.get_all_level_actors():
            if isinstance(start,unreal.PlayerStart):
                start.set_actor_location(unreal.Vector(-620,1240,1107),False,True)
                start.set_actor_rotation(unreal.Rotator(pitch=0,yaw=180,roll=0),True)
        refs={}
        refs['MemorialActor'],refs['ClinicRecordActor'],refs['HarborRecordActor']=build_memorial(mats,register_mat,departure_mat)
        (refs['HealerActor'],refs['WaterActor'],refs['LinenTrayActor'],refs['ClinicInstallActor'],refs['ClinicCoverActor'])=build_clinic(mats)
        (refs['SelaActor'],refs['LinenActor'],refs['CanvasActor'],refs['HarborInstallActor'],refs['HarborCoverActor'],refs['NeriHarborDestinationActor'])=build_shop_and_harbor(mats)
        refs['NeriActor']=npc('past.neri','Opening - Neri',(120,1050,floor_z(1050)),
                             '/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple',.88,150)
        refs['MotherHomeDestinationActor']=marker('Opening.MotherHomeDestination','Opening - Mother home endpoint',(-915,1412,1011))
        build_past_roof_patches(mats)
        # Existing family-room content appears only in the present. The same
        # stable Mother actor is reused; no second Mother is introduced.
        for actor in ACTORS.get_all_level_actors():
            if actor.actor_has_tag('npc.mother') or any(actor.actor_has_tag(tag) for tag in [
                'home.photo','home.letter','home.workbench','home.drawer','home.calibration_component',
                'Opening.WatchFace','Opening.WatchHand','Opening.WatchStrapA','Opening.WatchStrapB',
                'Opening.PartsBoxBase','Opening.PartsBoxBack','Opening.PartsBoxFront','Opening.PartsBoxLeft','Opening.PartsBoxRight']):
                add_tags(actor,'Opening.PresentOnly')
            component=actor.get_component_by_class(unreal.StaticMeshComponent)
            mesh=component.get_editor_property('static_mesh') if component else None
            if mesh and mesh.get_name()=='SM_Home_Rubble':
                # This group has no gameplay collision. Shared intact floors and
                # the visible collapsed-wing barricade remain untouched.
                add_tags(actor,'Opening.PresentOnly','Opening.Decorative')
        all_actors=ACTORS.get_all_level_actors()
        arrays={
            'PastActors':[a for a in all_actors if a.actor_has_tag('Opening.PastOnly')],
            'PresentActors':[a for a in all_actors if a.actor_has_tag('Opening.PresentOnly')],
            'PastCollisionActors':[a for a in all_actors if a.actor_has_tag('Opening.PastOnly') and
                (a.actor_has_tag('Opening.Interactable') or a.actor_has_tag('Opening.Blocking'))],
        }
        assigned=[];missing=[]
        for key,value in dict(refs,**arrays,**animations).items():
            try:manager.get_editor_property(key)
            except Exception:missing.append(key);continue
            manager.set_editor_property(key,value);assigned.append(key)
        if missing:report['warnings'].append({'map':map_path,'manager_fields_not_yet_declared':missing})
        if not LEVELS.save_current_level():raise RuntimeError('Cannot save authored chapter scene '+map_path)
        report['maps'].append({'path':map_path,'assigned_manager_fields':assigned,
            'references':{key:{'actor':value.get_path_name(),'position_cm':[value.get_actor_location().x,
                          value.get_actor_location().y,value.get_actor_location().z],
                          'tags':[str(t) for t in value.get_editor_property('tags')]} for key,value in refs.items()},
            'past_actor_count':len(arrays['PastActors']),'present_actor_count':len(arrays['PresentActors']),
            'safe_route_floor':'Existing promenade: Zcm = 1020 - 0.1 * Ycm; center lane remains clear',
            'new_game_start_cm':[-620,1240,1107],
            'load_and_anchor_start_cm':[120,1240,991],
            'npc_animation_assets':{key:value.get_path_name() for key,value in animations.items()},
            'mother_home_waypoints_cm':[[-430,1240,1011],[-600,1240,1011],[-760,1240,1011],[-915,1240,1011],[-915,1412,1011]],
            'standing_points_cm':{
                'NeriActor':[[-35,1050,floor_z(1050)+98]],
                'HealerActor':[[20,580,floor_z(580)+98]],
                'SelaActor':[[-25,-300,floor_z(-300)+98]],
                'WaterActor':[[0,640,floor_z(640)+98]],
                'LinenActor':[[0,-235,floor_z(-235)+98]],
                'LinenTrayActor':[[0,520,floor_z(520)+98]],
                'CanvasActor':[[0,-365,floor_z(-365)+98]],
                'ClinicInstallActor':[[20,390,floor_z(390)+98]],
                'HarborInstallActor':[[-60,-535,floor_z(-535)+98]],
                'MemorialActor':[[-245,1510,1109]],
            },
            'runtime_visibility_contract':'Enable collision only on Opening.Interactable or Opening.Blocking; override quest item visibility and committed outcome refs after generic era visibility.'})
    unreal.EditorAssetLibrary.save_directory('/Game/Opening',only_if_is_dirty=True,recursive=True)
    report['success']=True
    (PROJECT/'chapter2_scene_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    print(json.dumps(build_scene2(),indent=2))
