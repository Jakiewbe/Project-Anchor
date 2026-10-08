"""Thin installed adapter. No business logic, shell command building or fallback."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    folder = Path(__file__).resolve().parents[1]
    try:
        runtime = json.loads((folder / "runtime.json").read_text(encoding="utf-8-sig"))
        if not isinstance(runtime, dict) or runtime.get("schema") != 1:
            raise ValueError("不支持的定位文件版本")
        kit, interpreter, home = (Path(runtime[key]) for key in ("kit", "python", "codex_home"))
        if not kit.is_absolute() or not interpreter.is_absolute() or not home.is_absolute():
            raise ValueError("安装定位信息必须使用绝对路径")
        if not kit.is_file() or not interpreter.is_file():
            raise ValueError("工具箱或 Python 已迁移/缺失，请重新 install-global")
        version = subprocess.run([str(interpreter), "-X", "utf8", str(kit), "--version"],
                                 capture_output=True, encoding="utf-8", timeout=10)
        if version.returncode or version.stdout.strip() != runtime["version"]:
            raise ValueError("安装定位版本与实际工具箱不同，请重新 install-global")
        if len(sys.argv) > 1 and sys.argv[1] == "--locate":
            print(json.dumps(runtime, ensure_ascii=False))
            return 0
        env = dict(os.environ, CODEX_HOME=str(home), PYTHONUTF8="1")
        # Preserve the target project's cwd, UTF-8 stdin and native return code.
        return subprocess.run([str(interpreter), "-X", "utf8", str(kit), *sys.argv[1:]], env=env).returncode
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: codex-rules Skill 调用失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
