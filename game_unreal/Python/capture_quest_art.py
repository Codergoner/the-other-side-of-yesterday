"""Asynchronous, unsaved native Quest-map art A/B review.

Run in a dedicated Unreal editor process after the Quest district is saved.
Captures are editor SceneCapture2D output, never automatic headset evidence.
No map/asset save, campaign state, save slot or configuration write is called.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, re, sys, time, traceback
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT / 'Python'))
import capture_brief_art as base
import quest_scenery as scenery

MAP = '/Game/Quest/Maps/Verdant_Desktop'
HOUSE_HERO = '-questarthousehero' in unreal.SystemLibrary.get_command_line().lower()
PREMIUM_SKY_PROBE = '-questartpremiumprobe' in unreal.SystemLibrary.get_command_line().lower()
PREMIUM_REVIEW = HOUSE_HERO or PREMIUM_SKY_PROBE or '-questartpremiumreview' in unreal.SystemLibrary.get_command_line().lower()
MOBILE_REVIEW = PREMIUM_REVIEW or '-questartmobilepreview' in unreal.SystemLibrary.get_command_line().lower()
WIDTH, HEIGHT, EYE = 1600, 900, 162.0
VIEWS = [
    {'id': 'HomeFrontage', 'xy': [180, 1800], 'ground': 'street', 'target': [-750, 1300, 1400], 'fov': 88},
    {'id': 'SurvivingRoom', 'xy': [-620, 1240], 'ground': 'house', 'target': [-950, 1360, 1150], 'fov': 82},
    {'id': 'UphillCathedral', 'xy': [0, 1100], 'ground': 'street', 'target': [850, -6400, 2750], 'fov': 80},
    {'id': 'HarborVista', 'xy': [0, -700], 'ground': 'street', 'target': [4800, -2600, 650], 'fov': 78},
]
HERO_VIEWS = [{'id': 'WholeHouseCinematic', 'position_cm': [750, 1600, 1300],
               'target': [-650, 1250, 1370], 'fov': 75}]
ACTIVE_VIEWS = HERO_VIEWS if HOUSE_HERO else VIEWS
PROFILES = ['QuestBalanced', 'QuestSoft', 'QuestGolden']
if MOBILE_REVIEW or '-questartfinal' in unreal.SystemLibrary.get_command_line().lower():
    PROFILES = [scenery.DEFAULT_PROFILE]
if PREMIUM_SKY_PROBE:
    PROFILES = ['PremiumSky010', 'PremiumSky005']
base.CVARS = list(dict.fromkeys(base.CVARS + [
    'r.MobileHDR', 'r.ForwardShading', 'r.Mobile.ShadingPath',
    'r.Mobile.AntiAliasing', 'r.MobileMSAA', 'r.MSAACount',
    'vr.MobileMultiView', 'vr.InstancedStereo', 'r.DefaultFeature.AutoExposure',
    'r.Mobile.AllowMovableDirectionalLights', 'r.Mobile.EnableMovableLightCSMShaderCulling',
    'r.Mobile.SupportsGen4TAA', 'r.MobileNumDynamicPointLights',
]))


def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def exposure(settings):
    # Deliberately do not call harbor_lighting.exposure: its -11.5 bias belongs
    # to the protected desktop calibration, not these low-intensity candidates.
    for field, v in {'auto_exposure_method': unreal.AutoExposureMethod.AEM_MANUAL,
                     'auto_exposure_bias': 0.0,
                     'auto_exposure_apply_physical_camera_exposure': False,
                     'motion_blur_amount': 0.0, 'bloom_intensity': 0.0}.items():
        settings.set_editor_property('override_' + field, True)
        settings.set_editor_property(field, v)
    return settings


class QuestCapture(base.ArtCapture):
    def tick(self, delta):
        # finish_loading_before_screenshot can pump Slate while mobile shaders
        # compile. Ignore nested callbacks instead of recursively configuring
        # the same view from inside the loading wait.
        if getattr(self, '_tick_active', False):
            return
        self._tick_active = True
        try:
            super().tick(delta)
        finally:
            self._tick_active = False

    def write(self):
        super().write()
        (self.folder/'report.json').write_text(json.dumps(self.report,indent=2,default=str),encoding='utf-8')

    def __init__(self):
        if ROOT.parent.name != 'Quest_20261025':
            raise RuntimeError('Quest review is restricted to the protected Quest project')
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
        self.folder = ROOT / 'validation' / ('quest_house_hero_preview' if HOUSE_HERO else 'quest_premium_sky_probe' if PREMIUM_SKY_PROBE else 'quest_premium_mobile_preview' if PREMIUM_REVIEW else 'quest_mobile_preview' if MOBILE_REVIEW else 'quest_art') / self.stamp
        self.folder.mkdir(parents=True, exist_ok=False)
        self.report_path = ROOT / ('quest_house_hero_preview_report.json' if HOUSE_HERO else 'quest_premium_sky_probe_report.json' if PREMIUM_SKY_PROBE else 'quest_premium_mobile_preview_report.json' if PREMIUM_REVIEW else 'quest_mobile_preview_report.json' if MOBILE_REVIEW else 'quest_art_render_report.json')
        if MOBILE_REVIEW and (ROOT / 'quest_art_render_report.json').exists():
            (self.folder / 'desktop_latest_report_preserved.json').write_bytes((ROOT / 'quest_art_render_report.json').read_bytes())
        if PREMIUM_REVIEW and (ROOT / 'quest_mobile_preview_report.json').exists():
            (self.folder / 'foundation_mobile_report_preserved.json').write_bytes((ROOT / 'quest_mobile_preview_report.json').read_bytes())
        self.report = {
            'success': False, 'run': self.stamp,
            'scope': 'Native editor art A/B; no PIE, APK, headset or frame-rate claim',
            'renderer': 'SceneCapture2D FinalColorLDR -> RGBA8 target, target_gamma 2.2',
            'capture_limit': 'MobileHDR off can alter scene-capture output. Inspect native images; this is not a substitute for device stereoscopic validation.',
            'resolution': [WIDTH, HEIGHT], 'test_map': MAP,
            'camera_policy': 'All profiles share traced ground + 162cm, world position, target and horizontal FOV. These are review cameras, never headset FOV settings.',
            'ground_policy': 'Every view requires an actual visibility trace within 40cm of the existing authored floor; formula-only eye-height proof is refused.',
            'eye_height_cm': EYE, 'profiles': scenery.PROFILES,
            'images': [], 'pixel_samples': [], 'view_coordinates': {},
            'era_previews': [], 'diagnostics': [], 'lighting_previews': [],
            'warnings': [], 'cleanup_errors': [],
            'gameplay_tested': False, 'story_flags_modified': False,
            'save_profiles_written': False, 'asset_save_calls': False,
            'references_projected': False,
            'mobile_preview_requested': MOBILE_REVIEW,
            'premium_art_review': PREMIUM_REVIEW,
            'requested_device_profile': 'Meta_Quest_3' if MOBILE_REVIEW else None,
        }
        if HOUSE_HERO:
            self.report.update({'scope': 'Cinematic 3D house-layout art review in mobile preview; not a player/standing/headset view',
                'camera_policy': 'Fixed cinematic camera in world space. Horizontal FOV75 is for this artwork review only and does not change headset/gameplay FOV.',
                'ground_policy': 'No floor or standing-height proof is attempted. This camera can be outside the playable route.',
                'eye_height_cm': None, 'playable_eye_height_verified': False,
                'cinematic_review_only': True, 'headset_fov_modified': False})
        self.groups = [
            {'label': name, 'map': MAP, 'era': 'Present', 'jobs': [(v, 'Lit') for v in ACTIVE_VIEWS] + ([(VIEWS[0], mode) for mode in ['BaseColor', 'LightingOnly']] if name == 'QuestBalanced' and not HOUSE_HERO else [])}
            for name in PROFILES
        ]
        if PREMIUM_SKY_PROBE:
            for group, scale in zip(self.groups, [.10, .05]):
                group['lighting_profile'] = scenery.DEFAULT_PROFILE
                group['premium_sky_scale_override'] = scale
            self.report['premium_sky_probe'] = {'PremiumSky010': .10, 'PremiumSky005': .05}
        self.group_index = self.job_index = self.frame_count = 0
        self.phase = 'load'
        self.phase_time = time.monotonic()
        self.handle = None
        self.finished = False
        self.world = self.capture = self.component = self.target = None
        self.visibility = []
        self.cvar_restore = {}
        self.fixed_views = {}
        self.default_flags = None
        self.protected = {}
        files = [ROOT / 'Content' / (MAP.removeprefix('/Game/') + '.umap'),
                 ROOT / 'YesterdayHarbor.uproject', scenery.REPORT,
                 *(ROOT / 'Config').glob('*.ini'),
                 *(ROOT / 'Content' / 'Quest' / 'Scenery').rglob('*.uasset')]
        if PREMIUM_REVIEW:
            files += [ROOT / 'quest_premium_art_report.json', *(ROOT / 'Content' / 'Quest' / 'PremiumArt').rglob('*.uasset')]
        for file in files:
            if not file.is_file():
                raise RuntimeError('Required saved Quest capture input missing: ' + str(file))
            self.protected[file] = digest(file)
        original = json.loads(scenery.REPORT.read_text(encoding='utf-8'))
        self.saved_scenery_record = original['maps'][MAP]
        if not self.saved_scenery_record.get('success'):
            raise RuntimeError('Saved Quest scenery application has not succeeded')

    def metadata(self):
        result = super().metadata()
        observed = result.get('startup_log_metadata', {})
        platform = observed.get('shaderplatform', '').upper()
        level = observed.get('rhifeaturelevel', '').upper()
        if 'ES3_1' in level or any(k in platform for k in ['ES31', 'ES3_1', 'ANDROID']):
            kind = 'Editor mobile feature-level preview; not a Quest device'
        elif 'SM5' in level or 'SM6' in level or 'PCD3D_SM' in platform:
            kind = 'Desktop editor render; mobile preview not established'
        else:
            kind = 'Editor render; actual mobile feature level unverified'
        result['evidence_label'] = kind
        result['mobile_feature_level_verified'] = ('ES3_1' in level or 'ES31' in level) and any(k in platform for k in ['ES31', 'ES3_1'])
        result['headset_tested'] = False
        result['command_line'] = unreal.SystemLibrary.get_command_line()
        result['capture_exposure'] = {'method': 'Manual', 'bias': 0.0, 'physical_camera_exposure': False}
        if MOBILE_REVIEW:
            result['preview_limit'] = 'Desktop-hosted mobile feature-level rendering; Meta Quest profile selection is an emulation, not a device measurement.'
            try:
                active = str(unreal.EditorSubsystemBlueprintLibrary.get_preview_platform_name())
                result['active_preview_platform_from_native_api'] = active
                if active not in {'', 'None'} and any(k in active.upper() for k in ['ES3_1', 'ES31']):
                    result['mobile_feature_level_verified'] = True
                    result['evidence_label'] = 'Active ES3_1 editor preview; host RHI remains separate; not a Quest device'
                    result['active_preview_shader_platform'] = active.split(' ')[0]
                    result['preview_verification'] = 'Native active-preview API readback; Engine preview registry maps this shader platform to ES3_1 and the editor changes DefaultWorldFeatureLevel before loading the capture world.'
            except Exception as error:
                result['active_preview_query_error'] = str(error)
            file = result.get('startup_log')
            if file and Path(file).is_file():
                log = Path(file).read_text(encoding='utf-8', errors='replace')
                selected = re.findall(r'Selected Device Profile:\s*\[([^\]]+)\]', log)
                result['selected_device_profile_from_log'] = selected[-1] if selected else None
                result['requested_quest_profile_verified'] = bool(selected and selected[-1] == 'Meta_Quest_3')
                shader_evidence = [line for line in log.splitlines() if 'cached shadermap' in line and '_Preview' in line and 'ES3_1, Editor' in line]
                result['native_mobile_shader_compilation_evidence'] = shader_evidence[-12:]
        return result

    def start(self):
        if MOBILE_REVIEW:
            self.report['mobile_preview_setup'] = {'host_metadata_before': self.metadata()}
            library = unreal.EditorSubsystemBlueprintLibrary
            # GetPreviewPlatformOptions is a reflected UFUNCTION used by the
            # engine dropdown, without generated Python glue. call_method is
            # the documented native-reflection path for that exact function.
            options = [str(n) for n in unreal.get_default_object(library).call_method('GetPreviewPlatformOptions')]
            self.report['mobile_preview_setup']['available_native_options'] = options
            chosen = next((n for n in options if 'VULKAN_ES3_1_ANDROID' in n.upper() and n.endswith('Android_OpenXR')), None)
            if chosen is None:
                chosen = next((n for n in options if 'PCD3D_ES3_1' in n.upper() and n.endswith('Windows_Preview_ES31')), None)
            if chosen is None:
                raise RuntimeError('No verified ES3_1 shader-platform preview is available in the installed engine registry')
            self.report['mobile_preview_setup']['selected_native_option'] = chosen
            self.phase = 'preview_shader_compile'
            self.write()
            # Native implementation calls GEditor->SetPreviewPlatform(info,
            # false): no preview preference save is requested by this script.
            library.set_preview_platform(unreal.Name(chosen))
            active = str(library.get_preview_platform_name())
            if active != chosen:
                raise RuntimeError('Native preview API did not activate selected platform: ' + active)
            self.phase = 'load'
            self.phase_time = time.monotonic()
            self.report['runtime_metadata'] = self.metadata()
            if not self.report['runtime_metadata']['mobile_feature_level_verified']:
                raise RuntimeError('Requested mobile preview did not produce verified ES3_1 feature-level and shader-platform metadata; refusing mislabeled captures')
        super().start()

    def resolved_view(self, spec):
        ground, measurement = self.ground(spec)
        if measurement['method'] != 'Visibility trace checked against authored floor':
            raise RuntimeError('Quest eye-level capture requires actual floor support: ' + json.dumps({'view': spec['id'], **measurement}))
        if spec['id'] not in self.fixed_views:
            fixed = {'position_cm': [*spec['xy'], ground + EYE], 'target_cm': spec['target'],
                     'horizontal_fov': spec['fov'], 'reference_ground_cm': ground,
                     'reference_ground_measurement': measurement}
            self.fixed_views[spec['id']] = fixed
            self.report['view_coordinates'][spec['id']] = fixed
        fixed = self.fixed_views[spec['id']]
        check = {'ground_cm': ground, 'measurement': measurement,
                 'eye_height_above_current_ground_cm': fixed['position_cm'][2] - ground}
        if abs(check['eye_height_above_current_ground_cm'] - EYE) > 1:
            raise RuntimeError('Floor changed across lighting A/B at ' + spec['id'])
        return fixed, check

    def configure_view(self):
        if not HOUSE_HERO:
            return super().configure_view()
        group = self.groups[self.group_index]
        if self.job_index >= len(group['jobs']):
            self.next_group()
            return
        spec, mode = group['jobs'][self.job_index]
        if not self.configure_mode(mode):
            self.job_index += 1
            return
        unreal.AutomationLibrary.finish_loading_before_screenshot()
        position, target = unreal.Vector(*spec['position_cm']), unreal.Vector(*spec['target'])
        self.capture.set_actor_location(position, False, False)
        self.capture.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(position, target), False)
        self.component.set_editor_property('fov_angle', spec['fov'])
        fixed = {'position_cm': spec['position_cm'], 'target_cm': spec['target'], 'horizontal_fov': spec['fov']}
        self.report['view_coordinates'][spec['id']] = fixed
        self.current = {'label': group['label'], 'era': group['era'], 'map': MAP,
            'view': spec['id'], 'mode': mode, **fixed, 'editor_art_preview': True,
            'cinematic_review_only': True, 'playable_eye_height_verified': False,
            'current_ground_check': None, 'headset_fov_modified': False}
        self.frame_count = 0
        self.phase = 'warm'
        self.phase_time = time.monotonic()
        self.write()

    def load_group(self):
        self.restore_world()
        group = self.groups[self.group_index]
        if not self.level.load_level(MAP):
            raise RuntimeError('Cannot load saved Quest district ' + MAP)
        self.world = self.editor.get_editor_world()
        if not self.cvar_restore:
            self.set_session_cvars()
        transient = {'baseline': {}, 'inferred_manual_names': self.saved_scenery_record.get('inferred_manual_names', []),
                     'preserved_manual': [], 'unsupported_optional_properties': [],
                     'disabled_legacy_lights': [], 'touched_names': [], 'notes': []}
        # Call the unsaved internal helper, not set_lighting_profile(), so the
        # persisted generator after-snapshot stays aligned with the saved map.
        scenery.lighting(self.world, group.get('lighting_profile', group['label']), transient,
                         self.saved_scenery_record.get('after', {}), {})
        import build_quest_premium_art as premium
        if premium.enabled_for_map(MAP):
            self.report.setdefault('premium_lighting_previews', []).append(premium.preview_lighting(self.world, transient, group.get('premium_sky_scale_override')))
        self.report['lighting_previews'].append({'profile': group['label'], **transient})
        self.apply_era_preview('Present')
        self.capture = self.actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(pitch=0, yaw=0, roll=0), True)
        self.capture.set_actor_label('Quest transient A/B capture - NEVER SAVE')
        self.component = self.capture.get_component_by_class(unreal.SceneCaptureComponent2D)
        self.target = unreal.RenderingLibrary.create_render_target2d(self.world, WIDTH, HEIGHT,
            unreal.TextureRenderTargetFormat.RTF_RGBA8, unreal.LinearColor(1, 0, 1, 1), False, False)
        self.target.set_editor_property('target_gamma', 2.2)
        for field, v in [('texture_target', self.target), ('capture_every_frame', False),
                         ('capture_on_movement', False), ('always_persist_rendering_state', True)]:
            self.component.set_editor_property(field, v)
        self.component.set_editor_property('post_process_settings', exposure(self.component.get_editor_property('post_process_settings')))
        self.component.set_editor_property('post_process_blend_weight', 1.0)
        try:
            self.default_flags = list(self.component.get_show_flag_settings() if hasattr(self.component, 'get_show_flag_settings') else self.component.get_editor_property('show_flag_settings'))
        except Exception:
            self.default_flags = None
        self.phase = 'configure'
        self.phase_time = time.monotonic()
        self.write()

    def export(self):
        samples = []
        for yf in [.1, .3, .5, .7, .9]:
            for xf in [.1, .25, .5, .75, .9]:
                c = unreal.RenderingLibrary.read_render_target_pixel(self.world, self.target, int(WIDTH * xf), int(HEIGHT * yf))
                samples.append([int(c.r), int(c.g), int(c.b)])
        values = [c for rgb in samples for c in rgb]
        mean = sum(values) / len(values)
        pixel = {'profile': self.current['label'], 'view': self.current['view'], 'mode': self.current['mode'],
                 'min': min(values), 'max': max(values), 'mean': mean,
                 'variance': sum((v - mean) ** 2 for v in values) / len(values),
                 'samples': samples}
        self.report['pixel_samples'].append(pixel)
        if max(values) < 8 or pixel['variance'] < 2:
            self.report['warnings'].append({'capture_content_questionable': pixel})
        if self.current['view'] == 'SurvivingRoom' and mean < 25:
            self.report['warnings'].append({'room_readability_needs_review': pixel})
        filename = '_'.join(self.current[k] for k in ['label', 'era', 'view', 'mode']) + '.png'
        unreal.RenderingLibrary.export_render_target(self.world, self.target, str(self.folder), filename)
        file = self.folder / filename
        if not file.is_file() or file.stat().st_size < 10000:
            raise RuntimeError('Native PNG export failed: ' + str(file))
        self.report['images'].append({**self.current, 'profile': self.current['label'], 'path': str(file),
            'bytes': file.stat().st_size, 'sha256': digest(file), 'warm_frames': self.frame_count,
            'evidence_label': self.report['runtime_metadata']['evidence_label']})
        self.job_index += 1
        self.phase = 'configure'
        self.phase_time = time.monotonic()
        self.write()

    def finish(self, error=None):
        if self.finished:
            return
        self.finished = True
        if error:
            self.report['error'] = error
        if PREMIUM_REVIEW and self.world is not None:
            try:
                import build_quest_premium_art as premium
                self.report['premium_texture_resources'] = premium.measure_resources(self.world)
            except Exception:
                self.report['warnings'].append({'premium_resource_query_error': traceback.format_exc()})
        self.restore_world()
        for name, v in self.cvar_restore.items():
            try:
                unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), name + ' ' + v)
            except Exception:
                self.report['cleanup_errors'].append(traceback.format_exc())
        # Discard transient light candidates by reloading the existing saved map.
        try:
            self.report['saved_map_reloaded_for_cleanup'] = bool(self.level.load_level(MAP))
        except Exception:
            self.report['cleanup_errors'].append(traceback.format_exc())
        self.report['runtime_metadata'] = self.metadata()
        changed = [str(p) for p, h in self.protected.items() if not p.is_file() or digest(p) != h]
        self.report['protected_maps_assets_config_and_generator_report_unchanged'] = not changed
        self.report['unexpected_file_changes'] = changed
        self.report['protected_sha256'] = {str(p): h for p, h in self.protected.items()}
        required = {(name, view['id']) for name in PROFILES for view in ACTIVE_VIEWS}
        captured = {(row['profile'], row['view']) for row in self.report['images'] if row['mode'] == 'Lit'}
        self.report['required_profile_views_complete'] = required.issubset(captured)
        self.report['success'] = not error and not changed and not self.report['cleanup_errors'] and required.issubset(captured)
        if MOBILE_REVIEW:
            pixels = [p for p in self.report['pixel_samples'] if p['mode'] == 'Lit']
            self.report['mobile_preview_content_usable'] = bool(pixels) and all(p['max'] >= 8 and p['variance'] >= 2 for p in pixels)
            self.report['success'] = self.report['success'] and self.report['mobile_preview_content_usable'] and self.report['runtime_metadata']['mobile_feature_level_verified']
        self.phase = 'finished'
        self.write()
        if MOBILE_REVIEW:
            try:
                unreal.EditorSubsystemBlueprintLibrary.disable_preview_platform()
                self.report['mobile_preview_disabled_after_capture'] = str(unreal.EditorSubsystemBlueprintLibrary.get_preview_platform_name()) in {'', 'None'}
                self.write()
            except Exception:
                self.report['cleanup_errors'].append(traceback.format_exc())
                self.report['success'] = False
                self.write()
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()


def main():
    session = None
    try:
        session = QuestCapture()
        session.start()
    except Exception:
        error = traceback.format_exc()
        if session is not None:
            session.finish(error)
        else:
            (ROOT / ('quest_house_hero_preview_report.json' if HOUSE_HERO else 'quest_premium_sky_probe_report.json' if PREMIUM_SKY_PROBE else 'quest_premium_mobile_preview_report.json' if PREMIUM_REVIEW else 'quest_mobile_preview_report.json' if MOBILE_REVIEW else 'quest_art_render_report.json')).write_text(json.dumps({'success': False, 'scope': 'Quest native art capture setup', 'error': error}, indent=2), encoding='utf-8')
            unreal.EditorPythonScripting.set_keep_python_script_alive(False)
            unreal.SystemLibrary.quit_editor()


if __name__ == '__main__':
    main()
