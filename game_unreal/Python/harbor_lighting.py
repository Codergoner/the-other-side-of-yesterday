"""Shared, persisted golden-hour lighting for gameplay and native captures."""
import unreal


def exposure(settings):
    fields = {
        "auto_exposure_method":unreal.AutoExposureMethod.AEM_MANUAL,
        "auto_exposure_min_brightness":7.0,
        "auto_exposure_max_brightness":13.0,
        "auto_exposure_bias":-11.5,
        "auto_exposure_speed_up":3.0,
        "auto_exposure_speed_down":3.0,
        "auto_exposure_apply_physical_camera_exposure":False,
    }
    for key,value in fields.items():
        settings.set_editor_property("override_"+key,True)
        settings.set_editor_property(key,value)
    return settings


def configure(actors):
    has_fill = False
    for actor in actors:
        if isinstance(actor,unreal.DirectionalLight):
            light = actor.get_component_by_class(unreal.DirectionalLightComponent)
            if actor.get_actor_label() == "Soft sky bounce fill":
                has_fill = True
                actor.set_actor_rotation(unreal.Rotator(pitch=-55,yaw=-45,roll=0),False)
                light.set_intensity(2000.0)
                light.set_light_color(unreal.LinearColor(0.60,0.75,1.0,1))
                light.set_editor_property("cast_shadows",False)
                light.set_editor_property("atmosphere_sun_light",False)
            else:
                actor.set_actor_rotation(unreal.Rotator(pitch=-15,yaw=135,roll=0),False)
                light.set_intensity(20000.0)
                light.set_light_color(unreal.LinearColor(1.0,0.82,0.61,1))
        elif isinstance(actor,unreal.SkyLight):
            sky = actor.get_component_by_class(unreal.SkyLightComponent)
            sky.set_intensity(1.0)
            sky.set_editor_property("real_time_capture",False)
            sky.set_editor_property("lower_hemisphere_is_black",False)
            sky.recapture_sky()
        elif isinstance(actor,unreal.PostProcessVolume):
            actor.set_editor_property("settings",exposure(actor.get_editor_property("settings")))
        elif isinstance(actor,unreal.PlayerStart):
            actor.set_actor_rotation(unreal.Rotator(pitch=0,yaw=-90,roll=0),False)
    if not has_fill:
        fill = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(0,0,18000),unreal.Rotator(pitch=-55,yaw=-45,roll=0))
        fill.set_actor_label("Soft sky bounce fill")
        light = fill.get_component_by_class(unreal.DirectionalLightComponent)
        light.set_mobility(unreal.ComponentMobility.MOVABLE)
        light.set_intensity(2000.0)
        light.set_light_color(unreal.LinearColor(0.60,0.75,1.0,1))
        light.set_editor_property("cast_shadows",False)
        light.set_editor_property("atmosphere_sun_light",False)
