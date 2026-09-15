"""Keep an explicitly selected loopback demo process alive; no global power edits."""
import argparse
import ctypes
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attach-pid", type=int, required=True)
    ap.add_argument("--reference-workbook", required=True)
    ap.add_argument("--reference-extra", required=True)
    ap.add_argument("--reference-correction", action="append", default=[])
    ap.add_argument("--log-dir", type=Path, required=True)
    args = ap.parse_args()
    # Never stop a guessed process: check the executable's exact script argument.
    output = subprocess.check_output(["powershell", "-NoProfile", "-Command",
        f"Get-CimInstance Win32_Process -Filter 'ProcessId={args.attach_pid}' | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"], text=True)
    process = json.loads(output)
    count = ctypes.c_int()
    parse = ctypes.windll.shell32.CommandLineToArgvW
    parse.restype = ctypes.POINTER(ctypes.c_wchar_p)
    parse.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    pointer = parse(process["CommandLine"], ctypes.byref(count))
    argv = [pointer[i] for i in range(count.value)]
    ctypes.windll.kernel32.LocalFree(pointer)
    expected = (ROOT / "scripts/serve-operational-review.py").resolve()
    if len(argv) < 2 or Path(argv[1]).resolve() != expected:
        raise RuntimeError("Selected PID is not this repository's demo server")
    cmd = [str(ROOT / ".venv/Scripts/python.exe"), *argv[1:],
        "--reference-workbook", args.reference_workbook, "--reference-extra", args.reference_extra]
    for value in args.reference_correction:
        cmd.extend(["--reference-correction", value])
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "apps/backend/src"), str(ROOT / "scripts"), str(ROOT / "rag-pipeline")])
    env["PYTHONIOENCODING"] = "utf-8"
    args.log_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {args.attach_pid}"], check=True)
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    try:
        with (args.log_dir / "server.log").open("a", encoding="utf-8") as log:
            while True:
                child = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                (args.log_dir / "supervisor-state.json").write_text(json.dumps({
                    "supervisor_pid": os.getpid(), "server_launcher_pid": child.pid,
                    "started_at": time.time(), "log": str(args.log_dir / "server.log")}), encoding="utf-8")
                child.wait()
                time.sleep(3)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__ == "__main__":
    main()
