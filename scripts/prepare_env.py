"""Environment bootstrapper for ecom-tvc-studio: checks/installs dependencies and prints ENV_PY=<path>."""

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_DIR = os.path.join(ROOT, ".venv")
VENV_PY = os.path.join(VENV_DIR, "Scripts", "python.exe") if os.name == "nt" else os.path.join(VENV_DIR, "bin", "python")
REQ_FILE = os.path.join(ROOT, "requirements.txt")


def check_imports(py_exe: str) -> bool:
    try:
        subprocess.check_call(
            [py_exe, "-c", "import numpy, PIL, cv2, edge_tts"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true", help="Only check if environment is ready")
    args = p.parse_args()

    has_ffmpeg = shutil.which("ffmpeg") is not None
    if not has_ffmpeg:
        print("WARN: ffmpeg not found in PATH (required for rendering & audio mixing)")

    if os.path.exists(VENV_PY) and check_imports(VENV_PY):
        print(f"ENV_PY={VENV_PY}")
        return

    if check_imports(sys.executable):
        print(f"ENV_PY={sys.executable}")
        return

    if args.check:
        print("ENV_READY=false")
        raise SystemExit(1)

    if not os.path.exists(VENV_PY):
        print(f"Creating virtual environment at {VENV_DIR} ...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])

    print("Installing dependencies from requirements.txt ...")
    subprocess.check_call([VENV_PY, "-m", "pip", "install", "-q", "-r", REQ_FILE])
    print(f"ENV_PY={VENV_PY}")


if __name__ == "__main__":
    main()
