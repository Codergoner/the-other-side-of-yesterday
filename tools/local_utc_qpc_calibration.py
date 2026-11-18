"""Measured local UTC-to-QPC calibration. No capture, input or approval."""
from fractions import Fraction
from bisect import bisect_right

def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def build_local_utc_qpc_calibration(video_pairs, audio_pairs):
    """Invert actual bracketing UTC/QPC measurements, without media warping.

    UTC may smoothly slew relative to QPC. Both sources share QPC, so a single
    take-start UTC anchor accumulates a false offset. The video wrapper already
    measured the correspondence about four times per second. Use its adjacent
    precise UTC/QPC pairs to locate each packet UTC on the shared QPC clock.
    Audio's independent endpoint pairs must agree with that measured curve.

    These are clock measurements, not a claim about unknown display/audio
    presentation latency. Review of the actual aligned content stays required.
    """
    require(len(video_pairs) >= 3 and len(audio_pairs) >= 2,
            "Contemporaneous video and independent audio clock pairs required")
    require(max(p["half_bracket_ms"] for p in video_pairs + audio_pairs) <= 1,
            "Measured clock-pair uncertainty exceeds1ms")
    us = [Fraction(p["utc_filetime_100ns"]) for p in video_pairs]
    qs = [Fraction(p["qpc_midpoint_100ns"]) for p in video_pairs]
    require(all(b > a for a, b in zip(us, us[1:])) and
            all(b > a for a, b in zip(qs, qs[1:])),
            "Measured UTC/QPC calibration must be strictly increasing")
    spans = [(b-a)/10000000 for a, b in zip(qs, qs[1:])]
    require(max(spans) <= 1,
            "Local clock calibration has a gap over1second; no timing guess")
    steps = [float((us[i+1]-us[i])-(qs[i+1]-qs[i]))/10000
             for i in range(len(us)-1)]
    require(max(abs(x) for x in steps) <= 2,
            "Local UTC/QPC clock step exceeds2ms; no automatic jump repair")

    def convert(utc100ns, allow_endpoint_check=False):
        value = Fraction(utc100ns)
        if not allow_endpoint_check:
            require(us[0] <= value <= us[-1],
                    "Selected video packet is not bracketed by measured clocks")
        index = max(0, min(len(us)-2, bisect_right(us, value)-1))
        if value < us[0] or value > us[-1]:
            distance = min(abs(value-us[0]), abs(value-us[-1])) / 10000000
            require(allow_endpoint_check and distance <= 30,
                    "Independent audio endpoint is over30seconds outside video calibration")
        return qs[index] + (value-us[index])*(qs[index+1]-qs[index])/(us[index+1]-us[index])

    # Every interior observation is checked against the two neighboring actual
    # observations. This documents interpolation consistency independently of
    # the fact that a point maps exactly to itself.
    residuals = []
    for index in range(1, len(us)-1):
        expected = qs[index-1] + (us[index]-us[index-1]) * (
            qs[index+1]-qs[index-1]) / (us[index+1]-us[index-1])
        residuals.append(float(qs[index]-expected)/10000)
    require(max(abs(x) for x in residuals) <= 2,
            "Local leave-one-out clock calibration residual exceeds2ms")
    agreements = [float(convert(p["utc_filetime_100ns"], True)-p["qpc_midpoint_100ns"])/10000
                  for p in audio_pairs]
    require(max(abs(x) for x in agreements) <= 2,
            "Independent audio and video measured clock calibrations disagree over2ms")
    info = {
        "method": "inverse_piecewise_affine_measured_precise_UTC_to_shared_QPC",
        "video_pairs": len(video_pairs),
        "audio_pairs": len(audio_pairs),
        "selected_packets_must_be_bracketed": True,
        "max_calibration_spacing_seconds": float(max(spans)),
        "max_half_bracket_ms": max(p["half_bracket_ms"] for p in video_pairs + audio_pairs),
        "max_local_UTC_minus_QPC_step_ms": max(abs(x) for x in steps),
        "max_leave_one_out_residual_ms": max(abs(x) for x in residuals),
        "independent_audio_endpoint_residuals_ms": agreements,
        "max_independent_audio_endpoint_residual_ms": max(abs(x) for x in agreements),
        "max_system_minus_precise_UTC_ms": max(abs(p["system_minus_precise_ms"]) for p in video_pairs),
        "actual_video_global_UTC_minus_QPC_drift_ms": float((us[-1]-us[0])-(qs[-1]-qs[0]))/10000,
        "clock_slew_is_measured_not_assumed_zero": True,
        "media_timestamps_changed": False,
        "audio_resampled": False,
        "audio_playback_rate_changed": False,
        "reviewed_audio_video_sync": False,
        "limitation": "The local bound uses measured pair brackets, observed local/leave-one-out residuals and cross-recorder agreement. It excludes unobservable between-pair clock excursions and unknown WGC compositor/readback/audio render latency; actual sync review remains required.",
    }
    info["conservative_observed_calibration_error_bound_ms"] = (
        2*info["max_half_bracket_ms"] +
        info["max_local_UTC_minus_QPC_step_ms"] +
        info["max_leave_one_out_residual_ms"] +
        info["max_independent_audio_endpoint_residual_ms"] +
        info["max_system_minus_precise_UTC_ms"])
    return convert, info
