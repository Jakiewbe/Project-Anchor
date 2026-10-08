"""Skill distribution metadata; execution still uses the existing kit.py."""
from pathlib import Path
import sys
from . import VERSION
from .atomic_io import KitError, digest, encode_json, raw, safe_path
from .memory import KIT_ROOT


def skill_directory(parent=None):
    parent = Path(parent).expanduser().resolve() if parent else Path.home() / ".agents/skills"
    return safe_path(parent / "codex-rules", parent)


def skill_payload(home):
    source = KIT_ROOT / "skills/codex-rules"
    files = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    files["runtime.json"] = encode_json({"schema": 1, "version": VERSION,
                                        "kit": str(KIT_ROOT / "kit.py"),
                                        "python": str(Path(sys.executable).resolve()),
                                        "codex_home": str(Path(home).resolve())})
    return files


def prepare_skill(home, old_manifest, parent=None, uninstall=False):
    old = (old_manifest or {}).get("skill")
    target = Path(old["path"]) if old else skill_directory(parent)
    safe_path(target, target.parent)
    if old and parent is not None and skill_directory(parent) != target:
        raise KitError("不能在更新时改变 Skill 目录；先安全卸载，再安装到新位置")
    files = {} if uninstall else skill_payload(home)
    previous = old["hashes"] if old else {}
    if not old and target.exists() and any(p.is_file() or p.is_symlink() for p in target.rglob("*")):
        raise KitError("同名 Skill 已存在但不属于本安装；拒绝覆盖")
    expected, updates = {}, {}
    for name in sorted(set(files) | set(previous)):
        path = safe_path(target / name, target)
        current = raw(path)
        if name in previous:
            if current is None or digest(current) != previous[name]:
                raise KitError(f"Skill 管理文件已修改或缺失，拒绝覆盖: {name}")
        elif current is not None:
            raise KitError(f"Skill 新文件与用户文件冲突: {name}")
        expected[path] = current
        updates[path] = files.get(name)
    info = {"path": str(target), "version": VERSION,
            "hashes": {name: digest(data) for name, data in files.items()}}
    return target, updates, expected, info


def inspect_skill(home, manifest):
    info = manifest.get("skill")
    if not info:
        return [("UNVERIFIED", "Skill 安装", "旧版本未安装 Skill；重新 install-global")]
    target = Path(info["path"])
    expected = skill_payload(home)
    checks = [("PASS", "Skill 安装位置", str(target))]
    intact = all(raw(safe_path(target / name, target)) is not None and
                 digest(raw(target / name)) == value for name, value in info["hashes"].items())
    checks.append(("PASS" if intact else "FAIL", "Skill 安装完整性", "按安装清单检查所有管理文件"))
    current = {name: digest(data) for name, data in expected.items()}
    checks.append(("PASS" if current == info["hashes"] and info["version"] == VERSION else "WARN",
                   "Skill 模板版本", "模板、适配器和运行定位信息比对"))
    for path in (target / "runtime.json",):
        if not path.is_file():
            checks.append(("FAIL", "Skill 程序定位", "runtime.json 缺失"))
    checks.append(("UNVERIFIED", "Skill 原生发现与自动调用", "以真实 skills/list 和模型调用证据为准；描述匹配不保证每次自动触发"))
    return checks
