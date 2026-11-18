"""Master materials for Verdant. Vertex colour: R plaster/rockiness/shore, G occlusion, B soot,
A wind. Masonry samples in world space, so adjacent modules share one continuous surface and
no two buildings repeat. Era differences are material instances, never duplicated graphs.
"""
import unreal

import verdant_common as vc

MEL = unreal.MaterialEditingLibrary
PATH = vc.ROOT_PATH + '/Materials'
TEX = vc.ROOT_PATH + '/Textures/'


def tex(name):
    asset = unreal.load_asset(TEX + name)
    vc.require(asset is not None, 'Missing texture ' + name)
    return asset


class Graph:
    def __init__(self, name, two_sided=False, blend=None, shading=None):
        path = PATH + '/' + name
        self.mat = unreal.load_asset(path) if vc.library.does_asset_exist(path) else \
            vc.assets.create_asset(name, PATH, unreal.Material, unreal.MaterialFactoryNew())
        MEL.delete_all_material_expressions(self.mat)
        self.mat.set_editor_property('two_sided', two_sided)
        self.mat.set_editor_property('blend_mode', blend or unreal.BlendMode.BLEND_OPAQUE)
        self.mat.set_editor_property('shading_model', shading or unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
        self.mat.set_editor_property('use_material_attributes', False)
        self.x = -1600

    def node(self, cls):
        self.x += 20
        return MEL.create_material_expression(self.mat, cls, self.x, 0)

    def scalar(self, name, value):
        n = self.node(unreal.MaterialExpressionScalarParameter)
        n.set_editor_property('parameter_name', name)
        n.set_editor_property('default_value', value)
        return n

    def vector(self, name, colour):
        n = self.node(unreal.MaterialExpressionVectorParameter)
        n.set_editor_property('parameter_name', name)
        n.set_editor_property('default_value', unreal.LinearColor(*colour))
        return n

    def sample(self, texture, uv=None, kind=None):
        n = self.node(unreal.MaterialExpressionTextureSample)
        n.set_editor_property('texture', tex(texture))
        n.set_editor_property('sampler_type', kind or unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        if uv is not None:
            MEL.connect_material_expressions(uv, '', n, 'UVs')
        return n

    def normal(self, texture, uv=None):
        return self.sample(texture, uv, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)

    def masks(self, texture, uv=None):
        return self.sample(texture, uv, unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)

    def custom(self, code, inputs, kind=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
        n = self.node(unreal.MaterialExpressionCustom)
        n.set_editor_property('code', code)
        n.set_editor_property('output_type', kind)
        rows = []
        for key in inputs:
            row = unreal.CustomInput()
            row.set_editor_property('input_name', key)
            rows.append(row)
        n.set_editor_property('inputs', rows)
        for key, source in inputs.items():
            source, pin = source if isinstance(source, tuple) else (source, '')
            vc.require(MEL.connect_material_expressions(source, pin, n, key), 'Could not connect custom input ' + key)
        return n

    def world(self):
        return self.node(unreal.MaterialExpressionWorldPosition)

    def vnormal(self):
        return self.node(unreal.MaterialExpressionVertexNormalWS)

    def vertex(self):
        return self.node(unreal.MaterialExpressionVertexColor)

    def uv(self, tile=1.0):
        n = self.node(unreal.MaterialExpressionTextureCoordinate)
        n.set_editor_property('u_tiling', tile)
        n.set_editor_property('v_tiling', tile)
        return n

    def instance_data(self, index, default):
        n = self.node(unreal.MaterialExpressionPerInstanceCustomData)
        n.set_editor_property('data_index', index)
        n.set_editor_property('const_default_value', default)
        return n

    def out(self, prop, source, pin=''):
        vc.require(MEL.connect_material_property(source, pin, prop), 'Could not connect ' + str(prop))

    def done(self):
        MEL.recompile_material(self.mat)
        vc.library.save_loaded_asset(self.mat)
        return self.mat


BC, NRM, ROUGH, METAL, SPEC, AO, EMIT, OPMASK, WPO = (unreal.MaterialProperty.MP_BASE_COLOR, unreal.MaterialProperty.MP_NORMAL,
                                                      unreal.MaterialProperty.MP_ROUGHNESS, unreal.MaterialProperty.MP_METALLIC,
                                                      unreal.MaterialProperty.MP_SPECULAR, unreal.MaterialProperty.MP_AMBIENT_OCCLUSION,
                                                      unreal.MaterialProperty.MP_EMISSIVE_COLOR, unreal.MaterialProperty.MP_OPACITY_MASK,
                                                      unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
FLOAT2, FLOAT1 = unreal.CustomMaterialOutputType.CMOT_FLOAT2, unreal.CustomMaterialOutputType.CMOT_FLOAT1
BOX_UV = '''
float3 a = abs(N);
float2 uv = a.z > 0.7 ? P.xy : float2(a.y > a.x ? P.x : P.y, P.z);
return float2(uv.x, -uv.y) / Tile;
'''


def wind_offset(g, vc_node, amount, speed=1.6):
    """Cloth and leaves breathe; driven by vertex alpha so anchored edges stay put."""
    time = g.node(unreal.MaterialExpressionTime)
    wp = g.world()
    node = g.custom('''
float phase = dot(P.xy, float2(.011, .017)) + T * Speed;
float gust = sin(phase * .37) * .5 + .5;
return float3(sin(phase) + sin(phase * 2.3) * .4, cos(phase * 1.3) * .7, sin(phase * 1.7) * .25) * Weight * Amount * (.4 + gust);
''', {'P': wp, 'T': time, 'Weight': (vc_node, 'A'), 'Amount': g.scalar('WindAmount', amount), 'Speed': g.scalar('WindSpeed', speed)})
    g.out(WPO, node)


def masonry():
    g = Graph('M_V_Masonry')
    wp, n, v = g.world(), g.vnormal(), g.vertex()
    uv = g.custom(BOX_UV, {'P': wp, 'N': n, 'Tile': g.scalar('TileCm', 400)}, FLOAT2)
    uv_mask = g.custom('return UV * 1.33 + float2(.37, .11);', {'UV': uv}, FLOAT2)
    uv_broad = g.custom('return UV * .23;', {'UV': uv}, FLOAT2)
    lime, lime_n, lime_m = g.sample('T_V_Limestone_BC', uv), g.normal('T_V_Limestone_N', uv), g.masks('T_V_Limestone_ARH', uv)
    plas, plas_n, plas_m = g.sample('T_V_Plaster_BC', uv), g.normal('T_V_Plaster_N', uv), g.masks('T_V_Plaster_ARH', uv)
    mask, broad = g.masks('T_V_Masks', uv_mask), g.masks('T_V_Masks', uv_broad)
    tint = g.custom('return float3(R, G, B);', {'R': g.instance_data(0, 1.0), 'G': g.instance_data(1, .96), 'B': g.instance_data(2, .88)})
    cover = g.custom('''
float peel = Peel * .62 + Broad * .38;
float c = V.r + Bias;
// Hard-edged loss: plaster breaks off in patches, it does not fade.
return saturate((c - (peel * 1.05 - .1) * (1.0 - c * .15)) * 7.0);
''', {'V': v, 'Peel': (mask, 'R'), 'Broad': (broad, 'R'), 'Bias': g.scalar('PlasterBias', .0)}, FLOAT1)
    colour = g.custom('''
float3 lime = Lime * lerp(float3(1, 1, 1), float3(.6, .56, .5), Aging);
float3 base = lerp(lime, Plaster * Tint * float3(1.12, 1.03, .9), Cover);
float height = lerp(LimeH, .7, Cover);
// Grime gathers in low places and under the ledges the occlusion bake found.
float grime = saturate((1.0 - V.g) * .6) * (.55 + Broad * .6);
base *= lerp(float3(1, 1, 1), float3(.64, .6, .54), grime * GrimeAmount);
// Decades of weather: cooled, darkened, streaked, strongest where the broad field is high.
float age = Aging * saturate(.35 + Broad * 1.1);
base = lerp(base, dot(base, float3(.3, .6, .1)) * float3(.97, .92, .84), age * .55) * (1.0 - age * .3);
base = lerp(base, base * float3(.18, .17, .16), saturate(V.b * (.35 + Peel) * SootAmount));
return base;
''', {'Lime': lime, 'Plaster': plas, 'Tint': tint, 'Cover': cover, 'LimeH': (lime_m, 'B'), 'V': v, 'Broad': (broad, 'R'),
      'Peel': (mask, 'R'), 'GrimeAmount': g.scalar('GrimeAmount', .8),
      'Aging': g.scalar('Aging', .0), 'SootAmount': g.scalar('SootAmount', 1.2)})
    debug = g.custom('return Debug > .5 ? float3(V.r, V.g, V.b) : C;', {'Debug': g.scalar('Debug', 0.0), 'V': v, 'C': colour})
    g.out(BC, debug)
    nrm = g.custom('return normalize(lerp(LimeN, PlasterN, Cover));', {'LimeN': lime_n, 'PlasterN': plas_n, 'Cover': cover})
    g.out(NRM, nrm)
    rough = g.custom('return lerp(LimeR, PlasterR, Cover);', {'LimeR': (lime_m, 'G'), 'PlasterR': (plas_m, 'G'), 'Cover': cover}, FLOAT1)
    g.out(ROUGH, rough)
    occl = g.custom('return sqrt(saturate(V.g)) * lerp(LimeA, PlasterA, Cover);', {'V': v, 'LimeA': (lime_m, 'R'), 'PlasterA': (plas_m, 'R'), 'Cover': cover}, FLOAT1)
    g.out(AO, occl)
    return g.done()


def simple(name, base, normal, packed, tile=1.0, metallic=0.0, two_sided=False, brightness=1.0):
    """Timber, iron, terracotta: mesh UVs, baked occlusion, optional soot, per-material tint."""
    g = Graph(name, two_sided)
    uv = g.uv(tile)
    v = g.vertex()
    b, n, m = g.sample(base, uv), g.normal(normal, uv), g.masks(packed, uv)
    colour = g.custom('''
float3 c = B * Tint.rgb * Brightness;
c = lerp(c, dot(c, float3(.3, .6, .1)) * float3(.92, .9, .86), Aging * .55);
c *= lerp(.32, 1.0, saturate(V.g));
return lerp(c, c * .22, saturate(V.b * 1.6));
''', {'B': b, 'Tint': g.vector('Tint', (1, 1, 1, 1)), 'V': v, 'Aging': g.scalar('Aging', 0.0), 'Brightness': g.scalar('Brightness', brightness)})
    g.out(BC, colour)
    g.out(NRM, n)
    g.out(ROUGH, m, 'G')
    g.out(AO, g.custom('return V.g;', {'V': v}, FLOAT1))
    metal = g.scalar('Metallic', metallic)
    g.out(METAL, metal)
    return g.done()


def paint():
    """Painted shutters and doors: colour per building, chipping to bare timber as it ages."""
    g = Graph('M_V_Paint', True)
    uv, v = g.uv(1.0), g.vertex()
    wood, n, m = g.sample('T_V_Timber_BC', uv), g.normal('T_V_Timber_N', uv), g.masks('T_V_Timber_ARH', uv)
    wp = g.world()
    chip_uv = g.custom('return float2(P.x + P.y, P.z) / 90.0;', {'P': wp}, FLOAT2)
    chips = g.masks('T_V_Masks', chip_uv)
    tint = g.custom('return float3(R, G, B);', {'R': g.instance_data(3, .2), 'G': g.instance_data(4, .42), 'B': g.instance_data(5, .42)})
    colour = g.custom('''
float chipped = saturate((Peel * .8 + Chips * .2 - (1.0 - Aging * .6)) * 6.0);
float3 painted = Tint * (.55 + Wood.r * .5);
float3 c = lerp(painted, Wood * 1.7, chipped);
c = lerp(c, dot(c, float3(.3, .6, .1)) * float3(.9, .92, .92), Aging * .5);
c *= lerp(.32, 1.0, saturate(V.g));
return lerp(c, c * .25, saturate(V.b * 1.5));
''', {'Peel': (chips, 'R'), 'Chips': (chips, 'G'), 'Aging': g.scalar('Aging', 0.0), 'Tint': tint, 'Wood': wood, 'V': v})
    g.out(BC, colour)
    g.out(NRM, n)
    g.out(ROUGH, g.custom('return lerp(.46, R, Aging);', {'R': (m, 'G'), 'Aging': g.scalar('Aging', 0.0)}, FLOAT1))
    return g.done()


def roof():
    g = Graph('M_V_Roof', True)
    uv, v = g.uv(1.0), g.vertex()
    wp = g.world()
    b, n, m = g.sample('T_V_RoofTile_BC', uv), g.normal('T_V_RoofTile_N', uv), g.masks('T_V_RoofTile_ARH', uv)
    broad = g.masks('T_V_Masks', g.custom('return P.xy / 2600.0;', {'P': wp}, FLOAT2))
    speck = g.masks('T_V_Masks', g.custom('return P.xy / 330.0 + float2(.19, .67);', {'P': wp}, FLOAT2))
    # 17 November 2026 (concept pass): the entrant's atlas gives the houses terracotta roofs and keeps blue-green
    # for the Cathedral's caps ("Terracotta roofs and blue-green Cathedral caps separate the skyline into distinct
    # layers"). Clay 1 (the default, every kit roof) fires the same tile map as clay; the landmark instances
    # MI_V_RoofGlaze / MI_V_RoofGlaze_Present set Clay 0 and keep the glaze.
    colour = g.custom('''
float3 glaze = B * lerp(.82, 1.14, Broad);
float t = saturate(dot(B, float3(.3, .6, .1)) / .2);
float3 clay = lerp(ClayDark.rgb, ClayLight.rgb, t) * lerp(.78, 1.16, Broad) * lerp(.84, 1.1, Speck);
// Courses relaid over the years are paler.
clay = lerp(clay, clay * float3(1.14, 1.04, .9), smoothstep(.6, .8, Speck) * .5);
float3 c = lerp(glaze, clay, Clay);
// Sun-faded: glaze toward pale grey-green, clay toward a dusty pink; moss and salt with age.
float3 faded = lerp(float3(.96, 1.02, 1.0), float3(1.08, .95, .86), Clay);
c = lerp(c, dot(c, float3(.3, .6, .1)) * faded, .05 + Aging * lerp(.3, .42, Clay));
c = lerp(c, float3(.26, .27, .18), Aging * smoothstep(.45, .8, Broad) * .55);
return c * lerp(.45, 1.0, saturate(V.g)) * (1.0 - Aging * .22);
''', {'B': b, 'Broad': (broad, 'R'), 'Speck': (speck, 'B'), 'V': v, 'Aging': g.scalar('Aging', 0.0), 'Clay': g.scalar('Clay', 1.0),
      'ClayLight': g.vector('ClayLight', (.58, .17, .065, 1)), 'ClayDark': g.vector('ClayDark', (.2, .048, .02, 1))})
    g.out(BC, colour)
    g.out(NRM, n)
    g.out(ROUGH, g.custom('return saturate(R * .5 + .42);', {'R': (m, 'G')}, FLOAT1))
    return g.done()


def glass():
    g = Graph('M_V_Glass')
    wp, v = g.world(), g.vertex()
    time = g.node(unreal.MaterialExpressionTime)
    lit = g.custom('''
// V.r marks a lantern flame pane; other glass may be a lit room, chosen per window.
float2 cell = floor(float2(P.x + P.y, P.z) / 250.0);
float rnd = frac(sin(dot(cell, float2(12.9898, 78.233))) * 43758.5453);
float room = rnd < LitRooms ? .55 + .45 * rnd / max(LitRooms, .001) : 0.0;
float flame = V.r * (.82 + .18 * sin(T * 7.0 + P.x * .1));
return float3(1.0, .55, .22) * (room * RoomGain + flame * FlameGain);
''', {'P': wp, 'V': v, 'T': time, 'LitRooms': g.scalar('LitRooms', .12), 'RoomGain': g.scalar('RoomGain', .4), 'FlameGain': g.scalar('FlameGain', 2.5)})
    g.out(BC, g.vector('GlassTint', (.016, .022, .027, 1)))
    g.out(ROUGH, g.scalar('Roughness', .1))
    g.out(SPEC, g.scalar('Specular', .9))
    g.out(EMIT, lit)
    return g.done()


def story_glass():
    """See-through pane for the civic cases on the story map. M_V_Glass is the kit's window glass, an
    opaque dark mirror that hides whatever sits behind it; the memorial mounts and the chronology case
    must show their pages, so this one is translucent with a faint tint and a little specular."""
    g = Graph('M_V_Story_Glass', blend=unreal.BlendMode.BLEND_TRANSLUCENT)
    g.mat.set_editor_property('translucency_lighting_mode', unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    g.out(BC, g.vector('GlassTint', (.70, .76, .78, 1)))
    g.out(ROUGH, g.scalar('Roughness', .08))
    g.out(SPEC, g.scalar('Specular', .35))    # the evening sky's reflection must not wash out the pages
    g.out(unreal.MaterialProperty.MP_OPACITY, g.scalar('Opacity', .18))
    return g.done()


def flat():
    """Interior darkness and lamp bodies."""
    g = Graph('M_V_Flat')
    v, time = g.vertex(), g.node(unreal.MaterialExpressionTime)
    g.out(BC, g.custom('return float3(.03, .025, .02) * V.g;', {'V': v}))
    g.out(ROUGH, g.scalar('Roughness', .9))
    g.out(EMIT, g.custom('return V.r * float3(1.0, .6, .24) * Gain;', {'V': v, 'Gain': g.scalar('LampGain', 2.0)}))
    return g.done()


def cloth():
    g = Graph('M_V_Cloth', True)
    uv, v = g.uv(4.0), g.vertex()
    b, n = g.sample('T_V_Canvas_BC', uv), g.normal('T_V_Canvas_N', uv)
    # 17 November 2026 (concept pass): the reference boards dress the market in red and cream, not teal. The cloth
    # meshes carry their dye as vertex colour, so the teal one (and only it: green and blue well above red) is
    # re-dyed here instead of re-importing every awning, stall and pennant. Redye 0 gives the old cloth back.
    colour = g.custom('''
float3 dye = V.rgb;
float teal = saturate((min(dye.g, dye.b) - dye.r * 1.6) * 12.0) * Redye;
dye = lerp(dye, Madder.rgb * (.7 + dye.g), teal);
float3 c = dye * B;
c = lerp(c, dot(c, float3(.3, .6, .1)) * float3(.94, .9, .82), Aging * .6);
return c * (1.0 - Aging * .25);
''', {'V': v, 'B': b, 'Aging': g.scalar('Aging', 0.0), 'Redye': g.scalar('Redye', 1.0), 'Madder': g.vector('Madder', (.5, .075, .06, 1))})
    g.out(BC, colour)
    g.out(NRM, n)
    g.out(ROUGH, g.scalar('Roughness', .86))
    wind_offset(g, v, 16.0)
    return g.done()


def banner():
    """The gold tree on red cloth (T_V_Banner_BC, 17 November 2026). Aging fades and soils it for the one banner the
    present-day atlas leaves hanging among the damaged fronts."""
    g = Graph('M_V_Banner', True)
    uv, v = g.uv(1.0), g.vertex()
    b = g.sample('T_V_Banner_BC', uv)
    grime = g.masks('T_V_Masks', g.custom('return UV * float2(.6, 1.2) + float2(.31, .07);', {'UV': uv}, FLOAT2))
    g.out(BC, g.custom('''
float3 c = B;
c = lerp(c, dot(c, float3(.3, .6, .1)) * float3(1.0, .9, .82), Aging * .5);
return c * (1.0 - Aging * (.25 + Grime * .5));
''', {'B': b, 'Aging': g.scalar('Aging', 0.0), 'Grime': (grime, 'R')}))
    g.out(ROUGH, g.scalar('Roughness', .82))
    wind_offset(g, v, 26.0)
    return g.done()


def leaf():
    g = Graph('M_V_Leaf', True, unreal.BlendMode.BLEND_MASKED)
    uv, v = g.uv(1.0), g.vertex()
    b = g.sample('T_V_Foliage_BC', uv)
    colour = g.custom('''
float3 c = B * V.rgb;
c = lerp(c, dot(c, float3(.3, .6, .1)), .22);
return lerp(c, c * float3(1.12, .96, .68), Dry);
''', {'B': b, 'V': v, 'Dry': g.scalar('Dryness', .0)})
    g.out(BC, colour)
    g.out(OPMASK, b, 'A')
    g.out(ROUGH, g.scalar('Roughness', .62))
    g.out(SPEC, g.scalar('Specular', .3))
    wind_offset(g, v, 7.0, 1.1)
    g.mat.set_editor_property('opacity_mask_clip_value', .42)
    return g.done()


def paving(name, stem, tile):
    g = Graph(name)
    wp, v = g.world(), g.vertex()
    uv = g.custom('return float2(P.x, -P.y) / Tile;', {'P': wp, 'Tile': g.scalar('TileCm', tile)}, FLOAT2)
    broad_uv = g.custom('return UV * .17 + float2(.13, .41);', {'UV': uv}, FLOAT2)
    b, n, m = g.sample(stem + '_BC', uv), g.normal(stem + '_N', uv), g.masks(stem + '_ARH', uv)
    broad = g.masks('T_V_Masks', broad_uv)
    # 15 November 2026: most paving on the story map lies in building shade, lit by the blue sky alone. With the
    # first values (specular .42, polished crowns, full cavity occlusion) it read as pale blue fuzz between black
    # joints. The stone now carries a warm tint against the sky fill, is matt, and its joints keep some light.
    colour = g.custom('''
float3 c = B * Tint.rgb * lerp(.84, 1.12, Broad);
// Weeds root only in the joints, and only where the broad field lets them.
float joint = saturate((.42 - H) * 7.0);
float weed = joint * smoothstep(.42, .72, Broad) * Weeds;
c = lerp(c, float3(.17, .2, .08), weed);
c = lerp(c, dot(c, float3(.3, .6, .1)) * float3(.96, .93, .88), Aging * .5) * (1.0 - Aging * .22);
return c * lerp(.42, 1.0, saturate(V.g));
''', {'B': b, 'Tint': g.vector('Tint', (1.1, .98, .82, 1)), 'Broad': (broad, 'R'), 'H': (m, 'B'), 'Weeds': g.scalar('Weeds', 0.0),
      'Aging': g.scalar('Aging', 0.0), 'V': v})
    g.out(BC, colour)
    g.out(NRM, n)
    g.out(ROUGH, g.custom('return saturate(R * .3 + .66 + Aging * .06);', {'R': (m, 'G'), 'Aging': g.scalar('Aging', 0.0)}, FLOAT1))
    g.out(SPEC, g.scalar('Specular', .18))
    g.out(AO, g.custom('return V.g * lerp(1.0, A, Cavity);', {'V': v, 'A': (m, 'R'), 'Cavity': g.scalar('Cavity', .6)}, FLOAT1))
    return g.done()


def land():
    g = Graph('M_V_Land')
    wp, n_ws, v = g.world(), g.vnormal(), g.vertex()
    uv = g.custom(BOX_UV, {'P': wp, 'N': n_ws, 'Tile': g.scalar('RockTileCm', 2400)}, FLOAT2)
    uv2 = g.custom('return float2(P.x, -P.y) / 900.0;', {'P': wp}, FLOAT2)
    uv3 = g.custom('return float2(P.x, -P.y) / 18000.0;', {'P': wp}, FLOAT2)
    rock, rock_n, rock_m = g.sample('T_V_Rock_BC', uv), g.normal('T_V_Rock_N', uv), g.masks('T_V_Rock_ARH', uv)
    soil, soil_n = g.sample('T_V_Ground_BC', uv2), g.normal('T_V_Ground_N', uv2)
    broad = g.masks('T_V_Masks', uv3)
    # 15 November 2026: from the street the hills were one smooth tone (the 9 m and 24 m tiles average out at that
    # distance). Two mid-scale fields now break them up: lighter and darker ground, and patches of dry scrub.
    mid = g.masks('T_V_Masks', g.custom('return float2(P.x, -P.y) / 6200.0 + float2(.21, .57);', {'P': wp}, FLOAT2))
    mid2 = g.masks('T_V_Masks', g.custom('return float2(P.y, P.x) / 3700.0 + float2(.63, .09);', {'P': wp}, FLOAT2))
    # The rock again at six times the tile: its strata and ridges become the cliff's layering, readable from the street.
    far_rock = g.sample('T_V_Rock_BC', g.custom('return UV / 6.0 + float2(.31, .12);', {'UV': uv}, FLOAT2))
    colour = g.custom('''
float blend = saturate((V.r + (Broad - .5) * .5 - .42) * 5.0);
float layer = saturate((dot(FarRock, float3(.3, .6, .1)) - .1) / .3);
float3 rock = Rock * float3(.62, .56, .48) * lerp(.58, 1.3, layer);
float3 c = lerp(Soil, rock, blend) * lerp(.7, 1.1, Broad) * float3(.78, .74, .66);
c *= lerp(.72, 1.18, smoothstep(.3, .7, Mid.r));
float scrub = smoothstep(.5, .68, Mid2.r + (Mid.g - .5) * .5) * (1.0 - blend * .7) * Scrub;
c = lerp(c, float3(.15, .19, .09) * (.7 + Mid2.b * .7), scrub);
c *= lerp(1.0, .74, saturate(Mid2.g * 1.6 - .6) * blend);
return lerp(c, dot(c, float3(.3, .6, .1)) * float3(1.0, .94, .8), Dry);
''', {'V': v, 'Broad': (broad, 'R'), 'Mid': mid, 'Mid2': mid2, 'FarRock': far_rock, 'Soil': soil, 'Rock': rock, 'Dry': g.scalar('Dryness', .08),
      'Scrub': g.scalar('Scrub', .75)})
    g.out(BC, colour)
    g.out(NRM, g.custom('return normalize(lerp(S, R, saturate((V.r - .42) * 5.0)));', {'S': soil_n, 'R': rock_n, 'V': v}))
    g.out(ROUGH, g.scalar('Roughness', .9))
    return g.done()


def sea():
    """Opaque, cheap, and lit by the same sky the player sees. The sun path is real specular."""
    g = Graph('M_V_Sea')
    wp, v = g.world(), g.vertex()
    time = g.node(unreal.MaterialExpressionTime)
    cam = g.node(unreal.MaterialExpressionCameraPositionWS)
    near = g.custom('return float2(P.x - T * 12.0, -P.y + T * 7.0) / 1400.0;', {'P': wp, 'T': time}, FLOAT2)
    mid = g.custom('return float2(P.y + T * 19.0, P.x + T * 13.0) / 4600.0;', {'P': wp, 'T': time}, FLOAT2)
    far = g.custom('return float2(P.x + T * 26.0, -P.y - T * 18.0) / 21000.0;', {'P': wp, 'T': time}, FLOAT2)
    a, b, c = g.normal('T_V_Water_N', near), g.normal('T_V_Water_N', mid), g.normal('T_V_Water_N', far)
    n = g.custom('''
float d = distance(P, C);
float fadeNear = saturate(1.0 - d / 16000.0);
float fadeMid = saturate(1.0 - d / 90000.0);
// Far water calms so the sun path breaks into glints instead of shimmering.
float3 v = A * float3(fadeNear, fadeNear, 1) * .85 + B * float3(fadeMid, fadeMid, 1) * .8 + D * float3(1, 1, 1) * .55;
v.xy *= Strength;
return normalize(float3(v.xy, 1.6));
''', {'P': wp, 'C': cam, 'A': a, 'B': b, 'D': c, 'Strength': g.scalar('WaveStrength', 1.0)})
    g.out(NRM, n)
    colour = g.custom('''
float shallow = pow(saturate(V.r), 1.7);
float3 c = lerp(Deep.rgb, Shallow.rgb, shallow);
// Thin broken foam only where water meets stone.
float lace = saturate(V.r * 1.6 - .68 - Foam * .6 + sin(T * .9 + P.x * .012 + P.y * .009) * .08);
return lerp(c, float3(.62, .66, .62), lace * FoamAmount);
''', {'V': v, 'Deep': g.vector('DeepColor', (.014, .072, .096, 1)), 'Shallow': g.vector('ShallowColor', (.06, .24, .23, 1)),
      'Foam': (g.masks('T_V_Masks', g.custom('return P.xy / 500.0 + T * .015;', {'P': wp, 'T': time}, FLOAT2)), 'R'),
      'T': time, 'P': wp, 'FoamAmount': g.scalar('FoamAmount', .75)})
    g.out(BC, colour)
    g.out(ROUGH, g.scalar('Roughness', .22))
    g.out(SPEC, g.scalar('Specular', .26))
    return g.done()


def sky():
    g = Graph('M_V_Sky', True, None, unreal.MaterialShadingModel.MSM_UNLIT)
    g.mat.set_editor_property('is_sky', True)
    uv = g.uv(1.0)
    n = g.node(unreal.MaterialExpressionTextureSampleParameter2D)
    n.set_editor_property('parameter_name', 'SkyTexture')
    n.set_editor_property('texture', tex('T_V_Sky_Past'))
    n.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    MEL.connect_material_expressions(uv, '', n, 'UVs')
    g.out(EMIT, g.custom('return C * Gain;', {'C': n, 'Gain': g.scalar('SkyGain', 2.6)}))
    return g.done()


def instance(parent, name, scalars=None, vectors=None, textures=None):
    path = PATH + '/' + name
    mi = unreal.load_asset(path) if vc.library.does_asset_exist(path) else \
        vc.assets.create_asset(name, PATH, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property('parent', parent)
    for key, value in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(mi, key, value)
    for key, value in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(mi, key, unreal.LinearColor(*value))
    for key, value in (textures or {}).items():
        MEL.set_material_instance_texture_parameter_value(mi, key, value)
    vc.library.save_loaded_asset(mi)
    return mi


def build_all():
    made = {'Masonry': masonry(), 'Timber': simple('M_V_Timber', 'T_V_Timber_BC', 'T_V_Timber_N', 'T_V_Timber_ARH', brightness=1.7),
            'Iron': simple('M_V_Iron', 'T_V_Iron_BC', 'T_V_Iron_N', 'T_V_Iron_ARH', 2.0, .75),
            'Terracotta': simple('M_V_Terracotta', 'T_V_Plaster_BC', 'T_V_Plaster_N', 'T_V_Plaster_ARH', 1.0),
            'Paint': paint(), 'Roof': roof(), 'Glass': glass(), 'Flat': flat(), 'Cloth': cloth(), 'Banner': banner(), 'Leaf': leaf(),
            'Cobble': paving('M_V_Cobble', 'T_V_Cobble', 400), 'Flagstone': paving('M_V_Flagstone', 'T_V_Flagstone', 600),
            'Rock': land(), 'Sea': sea(), 'Sky': sky()}
    made['Ground'] = made['Rock']
    MEL.set_material_instance_vector_parameter_value  # keep attribute resolved early
    terracotta = instance(made['Terracotta'], 'MI_V_Terracotta', vectors={'Tint': (.82, .42, .26, 1)})
    made['Terracotta'] = terracotta
    # Present instances: the same materials, twenty years on.
    present = {'Masonry': instance(made['Masonry'], 'MI_V_Masonry_Present', {'Aging': .55, 'PlasterBias': .04, 'GrimeAmount': 1.0}),
               'Timber': instance(made['Timber'], 'MI_V_Timber_Present', {'Aging': .7}),
               'Iron': instance(made['Iron'], 'MI_V_Iron_Present', {'Aging': .6, 'Metallic': .3}),
               'Terracotta': instance(made['Terracotta'], 'MI_V_Terracotta_Present', {'Aging': .5}, {'Tint': (.72, .4, .26, 1)}),
               'Paint': instance(made['Paint'], 'MI_V_Paint_Present', {'Aging': .85}),
               'Roof': instance(made['Roof'], 'MI_V_Roof_Present', {'Aging': .7}),
               'Glass': instance(made['Glass'], 'MI_V_Glass_Present', {'LitRooms': .05, 'RoomGain': .5}, {'GlassTint': (.012, .014, .016, 1)}),
               'Cloth': instance(made['Cloth'], 'MI_V_Cloth_Present', {'Aging': .75}),
               'Leaf': instance(made['Leaf'], 'MI_V_Leaf_Present', {'Dryness': .25}),
               'Cobble': instance(made['Cobble'], 'MI_V_Cobble_Present', {'Aging': .55, 'Weeds': .9}),
               'Flagstone': instance(made['Flagstone'], 'MI_V_Flagstone_Present', {'Aging': .55, 'Weeds': .75})}
    instance(made['Masonry'], 'MI_V_Masonry_Debug', {'Debug': 1.0})
    sky_past = instance(made['Sky'], 'MI_V_Sky_Past', {'SkyGain': 1.35}, textures={'SkyTexture': tex('T_V_Sky_Past')})
    sky_present = instance(made['Sky'], 'MI_V_Sky_Present', {'SkyGain': 1.2}, textures={'SkyTexture': tex('T_V_Sky_Present')})
    return made, present, sky_past, sky_present
