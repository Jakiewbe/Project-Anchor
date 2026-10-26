"""Skill distribution metadata; execution still uses the existing kit.py."""
from pathlib import Path
import sys
from . import VERSION, NAME, LEGACY_NAME
from .atomic_io import KitError, digest, encode_json, raw, read_json, safe_path, same_path
from .memory import KIT_ROOT


def skill_directory(parent=None):
    parent = Path(parent).expanduser().resolve() if parent else Path.home() / ".agents/skills"
    return safe_path(parent / NAME, parent)


def skill_payload(home, client="codex"):
    source = KIT_ROOT / "skills" / NAME
    files = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    runtime = {"schema": 1, "version": VERSION, "kit": str(KIT_ROOT / "kit.py"),
               "python": str(Path(sys.executable).resolve())}
    # Codex keeps its original locator bytes; other clients never receive CODEX_HOME.
    if client == "codex":
        runtime["codex_home"] = str(Path(home).resolve())
    else:
        runtime.update(client=client, home=str(Path(home).resolve()))
    files["runtime.json"] = encode_json(runtime)
    return files


def _owner(target):
    try:
        runtime = read_json(target / "runtime.json")
        return f"{runtime['client']} ({runtime['home']})" if "client" in runtime else f"codex ({runtime['codex_home']})"
    except (KitError, OSError, KeyError, TypeError):
        return "未知来源"


def prepare_skill(home, old_manifest, parent=None, uninstall=False, client="codex"):
    old = (old_manifest or {}).get("skill")
    previous_target = Path(old["path"]) if old else None
    migrating = bool(old and previous_target.name == LEGACY_NAME and not uninstall)
    target = (skill_directory(previous_target.parent) if migrating else previous_target) if old else skill_directory(parent)
    safe_path(target, target.parent)
    if old and parent is not None and not same_path(skill_directory(parent), target):
        raise KitError("不能在更新时改变 Skill 目录；先安全卸载，再安装到新位置")
    files = {} if uninstall else skill_payload(home, client)
    previous = old["hashes"] if old and not migrating else {}
    if (not old or migrating) and target.exists() and any(p.is_file() or p.is_symlink() for p in target.rglob("*")):
        raise KitError(f"同名 Skill 已存在但不属于本安装，当前定位来源: {_owner(target)}；拒绝覆盖。"
                       "扫描同一目录的客户端可直接使用已安装 Skill；如需更换管理方，先用原安装命令卸载")
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
    if migrating:
        # Delete only legacy files owned by the verified manifest; keep user files.
        for name, expected_hash in old["hashes"].items():
            path = safe_path(previous_target / name, previous_target)
            current = raw(path)
            if current is None or digest(current) != expected_hash:
                raise KitError(f"旧 Skill 管理文件已修改或缺失，拒绝迁移: {name}")
            expected[path] = current
            updates[path] = None
    info = {"path": str(target), "version": VERSION,
            "hashes": {name: digest(data) for name, data in files.items()}}
    return target, updates, expected, info


def skill_scopes(manifest, target, legacy=False):
    """Derive authorized roots from the installed manifest, never from the journal."""
    roots = {"skill": target}
    old = (manifest or {}).get("skill")
    if old:
        previous = Path(old["path"])
        if not same_path(previous, target):
            if (not same_path(previous.parent, target.parent) or previous.name != LEGACY_NAME
                    or target.name != NAME):
                raise KitError("只允许在相同父目录从 codex-rules 迁移到 project-anchor")
            roots["legacy_skill"] = previous
    if legacy:
        if target.name != NAME:
            raise KitError("迁移恢复必须指定 project-anchor Skill 位置")
        roots["legacy_skill"] = safe_path(target.parent / LEGACY_NAME, target.parent)
    return roots


def inspect_skill(home, manifest, client="codex"):
    info = manifest.get("skill")
    if not info:
        return [("UNVERIFIED", "Skill 安装", "旧版本未安装 Skill；重新 install-global")]
    target = Path(info["path"])
    expected = skill_payload(home, client)
    checks = [("PASS", "Skill 安装位置", str(target))]
    modified = []
    for name, value in info["hashes"].items():
        data = raw(safe_path(target / name, target))
        if data is None or digest(data) != value:
            modified.append(name)
    checks.append(("FAIL" if modified else "PASS", "Skill 安装完整性",
                   "安装文件已修改或缺失，拒绝覆盖: " + ", ".join(sorted(modified)) if modified else "管理文件与安装清单一致"))
    current = {name: digest(data) for name, data in expected.items()}
    changed = sorted(name for name in set(current) | set(info["hashes"]) if current.get(name) != info["hashes"].get(name))
    up_to_date = not changed and info["version"] == VERSION
    detail = "模板与安装版本一致" if up_to_date else f"模板已更新：工具 {VERSION}，安装 {info['version']}"
    if changed:
        detail += "；待更新文件: " + ", ".join(changed)
    checks.append(("PASS" if up_to_date else "WARN", "Skill 模板版本", detail))
    for path in (target / "runtime.json",):
        if not path.is_file():
            checks.append(("FAIL", "Skill 程序定位", "runtime.json 缺失"))
    checks.append(("UNVERIFIED", "Skill 原生发现与自动调用", "以真实 skills/list 和模型调用证据为准；描述匹配不保证每次自动触发"))
    return checks
