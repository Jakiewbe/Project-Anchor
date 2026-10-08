"""Codex SessionStart entrypoint. stdin/stdout are UTF-8 JSON."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.hook_runtime import run

if __name__ == "__main__":
    raise SystemExit(run("SessionStart"))
