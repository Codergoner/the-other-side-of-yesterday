"""Launch one Release_20261026 Unreal editor Python job without a window.

Typed into Blender's Python console by the agent (the user chose on-screen driving):
    exec(open(r"<Release>\\tools\\launch_unreal_python.py", encoding="utf-8").read())
    launch("import_supporting_cast.py", "-SupportingCastImport")
Only scripts listed in ALLOWED (all inside game_unreal/Python) can be launched, and only
when no other Unreal editor process is running (one native writer at a time).
Each launch is recorded under output/supporting_cast/unreal_runs/.
"""
import json
import subprocess
import time
from pathlib import Path

RELEASE = Path(r"C:\Users\USER\OneDrive\Documents\ChatGPT\The other side of yesterday\development\Release_20261026")
PROJECT = RELEASE / "game_unreal" / "YesterdayHarbor.uproject"
EDITOR = Path(r"C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe")
RUNS = RELEASE / "output" / "supporting_cast" / "unreal_runs"
ALLOWED = {
    "import_supporting_cast.py",
    "integrate_supporting_cast.py",
    "validate_supporting_cast.py",
    "capture_supporting_cast.py",
    "audit_release_save_guard_final.py",
    "verify_release_key_persistence.py",
    "validate_release_additive_graphs.py",
}


def unreal_running():
    listing = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout.lower()
    return "unrealeditor" in listing


def launch(script, *flags, rhi="-nullrhi"):
    if script not in ALLOWED:
        raise RuntimeError("Not an allowed Release_20261026 Unreal job: " + script)
    path = RELEASE / "game_unreal" / "Python" / script
    if not path.is_file():
        raise RuntimeError("Missing job script: " + str(path))
    if unreal_running():
        raise RuntimeError("Another Unreal editor is already running; wait for it to exit.")
    for flag in flags:
        if not flag.startswith("-") or any(c in flag for c in '"&|<>^'):
            raise RuntimeError("Unsafe flag: " + flag)
    command = '"%s" "%s" -ExecutePythonScript="%s" %s -unattended -nop4 -nosplash %s' % (
        EDITOR, PROJECT, path.as_posix(), " ".join(flags), rhi)
    process = subprocess.Popen(command, creationflags=0x08000000)
    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    record = {"pid": process.pid, "script": script, "flags": list(flags), "rhi": rhi,
              "command": command, "started_utc": stamp}
    (RUNS / (stamp + "_" + script.replace(".py", "") + ".json")).write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("UNREAL JOB LAUNCHED", process.pid, script, " ".join(flags))
    return process.pid
