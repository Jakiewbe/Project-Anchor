"""Codex PreCompact entrypoint, never commits or blocks compaction."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.hook_runtime import run

if __name__ == "__main__":
    raise SystemExit(run("PreCompact"))
