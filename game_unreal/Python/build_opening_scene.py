"""Milestone A authored props for the existing Home maps.

Run build_scene() only after BP_OpeningActions has been compiled. This script
does not replace players, controllers, game modes, house geometry or lighting.
The small photo, paper, mannequin NPC and watch assembly are explicitly
temporary presentation assets. Their stable tags are gameplay identifiers.
"""
from pathlib import Path
import json
import math
import struct
import zlib
import unreal

PROJECT = Path(unreal.Paths.project_dir()).resolve()
ASSETS = unreal.AssetToolsHelpers.get_asset_tools()
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVELS = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
OWNED = 'Opening.SceneOwned'
MAPS = ['/Game/Home/Maps/House_FirstPerson', '/Game/Home/Maps/House_ThirdPerson']
MANAGER_PATH = '/Game/Opening/Blueprints/BP_OpeningActions.BP_OpeningActions_C'


def placed(local):
    x, y, z = local
    return unreal.Vector((-8-y)*100, (13-x)*100, (8.96+z)*100)


def png(path, width, height, pixels):
    """Write an original procedural prototype texture with stdlib only."""
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind+data)&0xffffffff)
    rows = b''.join(b'\x00'+bytes(pixels[y*width*3:(y+1)*width*3]) for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def make_presentation_textures():
    folder = PROJECT.parent/'output/opening/textures'
    folder.mkdir(parents=True, exist_ok=True)
    w, h = 640, 480
    data = bytearray(w*h*3)
    def rect(x0,y0,x1,y1,color):
        for yy in range(max(0,y0), min(h,y1)):
            for xx in range(max(0,x0), min(w,x1)):
                i=(yy*w+xx)*3; data[i:i+3]=bytes(color)
    def ellipse(cx,cy,rx,ry,color):
        for yy in range(max(0,cy-ry),min(h,cy+ry+1)):
            for xx in range(max(0,cx-rx),min(w,cx+rx+1)):
                if ((xx-cx)/rx)**2+((yy-cy)/ry)**2 <= 1:
                    i=(yy*w+xx)*3;data[i:i+3]=bytes(color)
    # Authored continuity: one adult (Mother) holding one baby. The father
    # took this photograph and is not pictured. Faces remain temporary art.
    rect(0,0,w,h,(58,34,20)); rect(12,12,w-12,h-12,(126,82,45))
    rect(23,23,w-23,h-23,(48,31,22)); rect(31,31,w-31,h-31,(208,188,150))
    rect(48,48,w-48,330,(174,163,139));rect(48,330,w-48,h-48,(110,108,87))
    rect(82,108,261,331,(191,177,144));rect(102,92,241,111,(83,78,63))
    rect(112,159,166,249,(89,91,78));rect(184,159,237,249,(89,91,78))
    ellipse(300,208,36,47,(74,66,53))
    ellipse(299,319,65,93,(77,73,59))
    rect(258,286,278,386,(77,73,59))
    # A small wrapped body lies across the adult's arms, with a single baby
    # head. There is no second adult silhouette, damaged face, or hidden face.
    ellipse(333,307,47,24,(160,148,118))
    ellipse(365,279,19,21,(104,95,75))
    ellipse(289,326,36,11,(82,76,60))
    ellipse(350,329,26,10,(82,76,60))
    # Speckling represents faded stock rather than printed identity details.
    for yy in range(35,h-35):
        for xx in range(35,w-35):
            i=(yy*w+xx)*3;delta=((xx*19+yy*31+(xx*yy)%71)%11)-5
            data[i:i+3]=bytes(max(0,min(255,c+delta)) for c in data[i:i+3])
    photo=folder/'T_FamilyPhoto_Provisional.png';png(photo,w,h,data)
    data=bytearray([202,185,148])*(w*h)
    rect(24,24,w-24,h-24,(222,207,174))
    for yy in range(114,390,31):
        rect(80,yy,520-(yy%3)*37,yy+3,(130,113,85))
    rect(80,73,260,81,(114,95,67))
    paper=folder/'T_Letter_Provisional.png';png(paper,w,h,data)
    return photo,paper


def make_photo_reverse_texture():
    """Prototype paper reverse with the authored inscription, and no extra text."""
    folder=PROJECT.parent/'output/opening/textures'
    folder.mkdir(parents=True,exist_ok=True)
    w,h=640,480
    data=bytearray(w*h*3)
    for y in range(h):
        for x in range(w):
            edge=min(x,y,w-1-x,h-1-y)
            shade=min(0,edge-27)//3+((x*17+y*23)%7)-3
            i=(y*w+x)*3
            data[i:i+3]=bytes(max(0,min(255,c+shade)) for c in (211,193,156))
    # Small original bitmap glyphs keep this source-only build independent of
    # external fonts or imaging packages in Unreal's bundled Python runtime.
    glyphs={
        'O':['01110','10001','10001','10001','10001','10001','01110'],
        'u':['00000','00000','10001','10001','10001','10011','01101'],
        'r':['00000','00000','10110','11001','10000','10000','10000'],
        'f':['00110','01001','01000','11100','01000','01000','01000'],
        'i':['00100','00000','01100','00100','00100','00100','01110'],
        's':['00000','00000','01111','10000','01110','00001','11110'],
        't':['01000','01000','11100','01000','01000','01001','00110'],
        'm':['00000','00000','11010','10101','10101','10101','10101'],
        'e':['00000','00000','01110','10001','11111','10000','01111'],
        'a':['00000','00000','01110','00001','01111','10001','01111'],
        'h':['10000','10000','10110','11001','10001','10001','10001'],
        'o':['00000','00000','01110','10001','10001','10001','01110'],
        '.':['00000','00000','00000','00000','00000','00110','00110'],
        ' ':['00000']*7,
    }
    inscription='Our first summer at home.'
    scale=3
    start_x=(w-len(inscription)*6*scale)//2
    for ci,char in enumerate(inscription):
        for row,bits in enumerate(glyphs[char]):
            for col,on in enumerate(bits):
                if on!='1':continue
                for dy in range(scale):
                    for dx in range(scale):
                        x=start_x+ci*6*scale+col*scale+dx+(6-row)//3
                        y=224+row*scale+dy
                        i=(y*w+x)*3;data[i:i+3]=bytes((88,70,48))
    path=folder/'T_FamilyPhotoReverse_Provisional.png'
    png(path,w,h,data)
    return path


def texture(file,force_reimport=False):
    name=file.stem
    path='/Game/Opening/Textures/'+name
    exists=unreal.EditorAssetLibrary.does_asset_exist(path)
    if exists and not force_reimport:
        return unreal.load_asset(path)
    task=unreal.AssetImportTask()
    task.set_editor_property('filename',str(file))
    task.set_editor_property('destination_path','/Game/Opening/Textures')
    task.set_editor_property('destination_name',name)
    task.set_editor_property('automated',True)
    task.set_editor_property('replace_existing',bool(exists))
    task.set_editor_property('replace_existing_settings',False)
    task.set_editor_property('save',True)
    ASSETS.import_asset_tasks([task])
    value=unreal.load_asset(path)
    if value is None:raise RuntimeError('Texture import failed: '+str(file))
    return value


def material(name,color=(.3,.2,.1),roughness=.75,metallic=0.0,image=None):
    path='/Game/Opening/Materials/'+name
    value=unreal.load_asset(path)
    if value is None:
        value=ASSETS.create_asset(name,'/Game/Opening/Materials',unreal.Material,unreal.MaterialFactoryNew())
    unreal.MaterialEditingLibrary.delete_all_material_expressions(value)
    if image:
        base=unreal.MaterialEditingLibrary.create_material_expression(value,unreal.MaterialExpressionTextureSample,-300,-100)
        base.set_editor_property('texture',image)
        unreal.MaterialEditingLibrary.connect_material_property(base,'RGB',unreal.MaterialProperty.MP_BASE_COLOR)
    else:
        base=unreal.MaterialEditingLibrary.create_material_expression(value,unreal.MaterialExpressionConstant3Vector,-300,-100)
        base.set_editor_property('constant',unreal.LinearColor(*color,1))
        unreal.MaterialEditingLibrary.connect_material_property(base,'',unreal.MaterialProperty.MP_BASE_COLOR)
    for parameter,number,y in [(unreal.MaterialProperty.MP_ROUGHNESS,roughness,50),(unreal.MaterialProperty.MP_METALLIC,metallic,150)]:
        node=unreal.MaterialEditingLibrary.create_material_expression(value,unreal.MaterialExpressionConstant,-300,y)
        node.set_editor_property('r',number)
        unreal.MaterialEditingLibrary.connect_material_property(node,'',parameter)
    unreal.MaterialEditingLibrary.recompile_material(value)
    unreal.EditorAssetLibrary.save_loaded_asset(value)
    return value


def owned_actor(stable_id,klass,label,local,rotation=None,interactive=False):
    matches=[a for a in ACTORS.get_all_level_actors() if a.actor_has_tag(stable_id)]
    if len(matches)>1:raise RuntimeError('Duplicate stable scene identifier '+stable_id)
    value=matches[0] if matches else None
    rotation=rotation or unreal.Rotator(pitch=0,yaw=0,roll=0)
    if value is None:
        value=ACTORS.spawn_actor_from_class(klass,placed(local),rotation)
    if not value:raise RuntimeError('Cannot create '+label)
    value.set_actor_label(label)
    value.set_actor_location(placed(local),False,False)
    value.set_actor_rotation(rotation,False)
    tags=[unreal.Name(OWNED),unreal.Name(stable_id)]
    if interactive:tags.append(unreal.Name('Opening.Interactable'))
    value.set_editor_property('tags',tags)
    value.set_folder_path('Opening/Playable objects' if interactive else 'Opening/Scene dressing')
    return value


def mesh_actor(stable_id,label,local,dimensions,mat,shape='Cube',interactive=False,movable=False,blocking=False,rotation=None):
    actor=owned_actor(stable_id,unreal.StaticMeshActor,label,local,rotation,interactive)
    component=actor.get_component_by_class(unreal.StaticMeshComponent)
    component.set_mobility(unreal.ComponentMobility.MOVABLE if movable else unreal.ComponentMobility.STATIC)
    component.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/'+shape))
    # Unreal primitives are 100cm wide/high; our dimensions are metres.
    actor.set_actor_scale3d(unreal.Vector(*dimensions))
    component.set_material(0,mat)
    component.set_simulate_physics(False)
    if blocking:
        component.set_collision_profile_name('BlockAll')
        component.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
    elif interactive:
        component.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
        component.set_collision_response_to_all_channels(unreal.CollisionResponseType.ECR_IGNORE)
        component.set_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY,unreal.CollisionResponseType.ECR_BLOCK)
    else:
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    # Actor-level collision survives native component profile reinitialization
    # when the saved level is loaded for play.
    actor.set_actor_enable_collision(bool(blocking or interactive))
    return actor


def beam(stable_id,a,b,mat,width=.12,depth=.12):
    aa,bb=placed(a),placed(b)
    midpoint=tuple((a[i]+b[i])*.5 for i in range(3))
    rotation=unreal.MathLibrary.find_look_at_rotation(aa,bb)
    return mesh_actor(stable_id,'Opening - Ruin barricade timber',midpoint,((bb-aa).length()/100,width,depth),mat,rotation=rotation,blocking=True)


def inspection_material(photo_texture,name='M_OpeningPhotoInspection'):
    path='/Game/Opening/Materials/'+name
    value=unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else ASSETS.create_asset(name,'/Game/Opening/Materials',unreal.Material,unreal.MaterialFactoryNew())
    unreal.MaterialEditingLibrary.delete_all_material_expressions(value)
    value.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
    value.set_editor_property('two_sided',True)
    value.set_editor_property('disable_depth_test',True)
    image=unreal.MaterialEditingLibrary.create_material_expression(value,unreal.MaterialExpressionTextureSample,-500,0);image.set_editor_property('texture',photo_texture)
    multiply=unreal.MaterialEditingLibrary.create_material_expression(value,unreal.MaterialExpressionMultiply,-200,0);multiply.set_editor_property('const_b',2200)
    unreal.MaterialEditingLibrary.connect_material_expressions(image,'RGB',multiply,'A')
    unreal.MaterialEditingLibrary.connect_material_property(multiply,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    opacity=unreal.MaterialEditingLibrary.create_material_expression(value,unreal.MaterialExpressionConstant,-200,150);opacity.set_editor_property('r',1)
    unreal.MaterialEditingLibrary.connect_material_property(opacity,'',unreal.MaterialProperty.MP_OPACITY)
    unreal.MaterialEditingLibrary.recompile_material(value);unreal.EditorAssetLibrary.save_loaded_asset(value)
    return value


def build_scene():
    photo_file,paper_file=make_presentation_textures()
    # Reimport into the existing texture path/asset rather than leaving the old
    # three-person temporary artwork cached or creating a parallel photo asset.
    photo_texture=texture(photo_file,force_reimport=True)
    inspect_material=inspection_material(photo_texture)
    reverse_texture=texture(make_photo_reverse_texture(),force_reimport=True)
    reverse_inspect_material=inspection_material(reverse_texture,'M_OpeningPhotoBackInspection')
    mats={
        'photo':material('M_OpeningFamilyPhoto',image=photo_texture),
        'paper':material('M_OpeningLetter',image=texture(paper_file)),
        'brass':material('M_OpeningRepairedBrass',(.31,.19,.055),.5,.65),
        'dial':material('M_OpeningWatchFace',(.63,.55,.38),.85,0),
        'dark':material('M_OpeningInk',(.015,.025,.025),.8,0),
        'wood':unreal.load_asset('/Game/Harbor/Materials/M_Wood'),
        'stone':unreal.load_asset('/Game/Harbor/Materials/M_Stone'),
        'dish':material('M_OpeningContactDish',(.43,.39,.29),.84,0),
    }
    if not mats['wood'] or not mats['stone']:raise RuntimeError('Existing house materials missing')
    report={'success':False,'maps':[],'temporary_presentation':[
        'Family photo depicts Mother holding a baby only; its sepia art remains a temporary presentation.',
        'The reverse inscription is exactly: Our first summer at home.',
        'Letter world mesh uses paper markings; the interaction panel supplies readable text.',
        'Mother reuses Epic Quinn and an unarmed idle; no bespoke NPC performance is implied.',
        'Watch assembly, contact dish and prepared contact use authored engine primitive stand-ins.'
    ]}
    for path in MAPS:
        if not LEVELS.load_level(path):raise RuntimeError('Cannot load existing map '+path)
        refs={}
        refs['PhotoActor']=mesh_actor('home.photo','Opening - Family photograph',(-.70,-.18,2.16),(.025,.32,.25),mats['photo'],interactive=True,movable=True)
        refs['LetterActor']=mesh_actor('home.letter','Opening - Personal letter',(.25,-.18,2.025),(.31,.22,.008),mats['paper'],interactive=True,movable=True)
        refs['BenchActor']=mesh_actor('home.workbench','Opening - Chronowatch workbench',(1.08,2.10,2.205),(.28,.28,.035),mats['brass'],'Cylinder',True,True)
        mesh_actor('Opening.WatchFace','Opening - Chronowatch dial',(1.08,2.10,2.229),(.24,.24,.012),mats['dial'],'Cylinder')
        mesh_actor('Opening.WatchHand','Opening - Chronowatch dial hand',(1.08,2.08,2.240),(.015,.10,.008),mats['dark'])
        mesh_actor('Opening.WatchStrapA','Opening - Repaired watch strap',(1.08,1.89,2.198),(.23,.14,.025),mats['wood'])
        mesh_actor('Opening.WatchStrapB','Opening - Repaired watch strap',(1.08,2.31,2.198),(.23,.14,.025),mats['wood'])
        # Reuse every old stable actor ID, but the new draft presents a prepared
        # contact in a shallow dish rather than a missing collar in a closed box.
        mesh_actor('Opening.PartsBoxBase','Opening - Shallow contact dish',(.1,2.12,2.16),(.40,.40,.035),mats['dish'])
        for suffix,at,dims in [
            ('Back',(.1,2.31,2.195),(.025,.40,.035)),('Front',(.1,1.93,2.195),(.025,.40,.035)),
            ('Left',(-.09,2.12,2.195),(.38,.025,.035)),('Right',(.29,2.12,2.195),(.38,.025,.035))]:
            mesh_actor('Opening.PartsBox'+suffix,'Opening - Contact dish rim',at,dims,mats['dish'])
        refs['DrawerActor']=mesh_actor('home.drawer','Opening - Retired parts-box lid reference',(.1,2.12,2.13),(.01,.01,.01),mats['dish'],movable=True)
        refs['DrawerActor'].set_actor_hidden_in_game(True)
        refs['DrawerActor'].set_actor_enable_collision(False)
        refs['ComponentActor']=mesh_actor('home.calibration_component','Opening - Prepared watch contact',(.1,2.09,2.184),(.07,.11,.012),mats['brass'],interactive=True,movable=True)
        refs['ComponentActor'].set_actor_hidden_in_game(False)
        # Native skeletal mesh, original reused idle, and no game-mode changes.
        mother=owned_actor('npc.mother',unreal.SkeletalMeshActor,'Opening - Mother',(-1.12,1.15,1.15),interactive=True)
        skel=mother.get_component_by_class(unreal.SkeletalMeshComponent)
        skel.set_mobility(unreal.ComponentMobility.MOVABLE)
        mesh=unreal.load_asset('/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple')
        idle=unreal.load_asset('/Game/Characters/Mannequins/Anims/Unarmed/MM_Idle')
        if mesh is None or idle is None:raise RuntimeError('Existing unarmed Mother stand-in assets unavailable')
        skel.set_skeletal_mesh_asset(mesh)
        skel.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        skel.play_animation(idle,True)
        skel.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
        skel.set_collision_response_to_all_channels(unreal.CollisionResponseType.ECR_IGNORE)
        skel.set_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY,unreal.CollisionResponseType.ECR_BLOCK)
        mother.set_actor_scale3d(unreal.Vector(.96,.96,.96))
        refs['MotherActor']=mother
        # Small island-style stone marker and repaired brass anchor face.
        mesh_actor('Opening.AnchorStone','Opening - Time anchor stone',(-1.5,-4.95,1.34),(.45,.45,.30),mats['stone'],'Cylinder')
        refs['AnchorActor']=mesh_actor('home.anchor','Opening - Home time anchor',(-1.5,-4.95,1.505),(.35,.35,.035),mats['brass'],'Cylinder',True,True)
        mesh_actor('Opening.AnchorMark','Opening - Anchor dial marking',(-1.5,-4.95,1.527),(.025,.25,.008),mats['dark'])
        # Clearly visible, continuous barrier across the damaged side doorway.
        for suffix,y in [('South',-.67),('North',1.27)]:
            beam('Opening.Barricade.'+suffix,(2.03,y,1.15),(2.03,y,3.08),mats['wood'],.16,.16)
        beam('Opening.Barricade.Rail',(2.03,-.67,2.02),(2.03,1.27,2.02),mats['wood'],.17,.15)
        beam('Opening.Barricade.CrossA',(2.03,-.67,1.42),(2.03,1.27,2.86),mats['wood'],.13,.13)
        beam('Opening.Barricade.CrossB',(2.03,-.67,2.86),(2.03,1.27,1.42),mats['wood'],.13,.13)
        barrier=mesh_actor('Opening.Barricade.CapsuleStop','Opening - Unsafe collapsed area barrier',(2.05,.30,2.17),(2.08,.16,2.04),mats['wood'],blocking=True)
        barrier.set_actor_hidden_in_game(True)
        manager_class=unreal.load_class(None,MANAGER_PATH)
        if manager_class is None:raise RuntimeError('Compile BP_OpeningActions before building the opening scene')
        managers=[actor for actor in ACTORS.get_all_level_actors() if actor.actor_has_tag('Opening.Manager')]
        if len(managers)>1:raise RuntimeError('Duplicate Opening.Manager actors')
        manager=managers[0] if managers else ACTORS.spawn_actor_from_class(manager_class,unreal.Vector(0,0,0),unreal.Rotator(pitch=0,yaw=0,roll=0))
        manager.set_actor_label('Opening - Chapter actions')
        manager.set_editor_property('tags',[unreal.Name(OWNED),unreal.Name('Opening.Manager')])
        manager.set_folder_path('Opening/Gameplay')
        manager.set_editor_property('SaveSlot','Yesterday_Brief_20261025')
        for name,actor in refs.items():manager.set_editor_property(name,actor)
        manager.set_editor_property('InspectionMaterial',inspect_material)
        try:manager.get_editor_property('PhotoBackInspectionMaterial')
        except Exception:pass  # The older opening-only manager predates this field.
        else:manager.set_editor_property('PhotoBackInspectionMaterial',reverse_inspect_material)
        if not LEVELS.save_current_level():raise RuntimeError('Cannot save authored Home map '+path)
        report['maps'].append({'path':path,'manager':manager.get_path_name(),'objects':[{'id':next(str(t) for t in actor.get_editor_property('tags') if str(t) not in[OWNED,'Opening.Interactable']), 'reference':key,'actor_path':actor.get_path_name(),'position_cm':[actor.get_actor_location().x,actor.get_actor_location().y,actor.get_actor_location().z]} for key,actor in refs.items()]})
    unreal.EditorAssetLibrary.save_directory('/Game/Opening',only_if_is_dirty=True,recursive=True)
    report['success']=True
    (PROJECT/'opening_scene_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    print(json.dumps(build_scene(),indent=2))
