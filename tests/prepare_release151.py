"""Build and independently read back a source-only ZIP, never publish it.

--commit packages that exact Git commit. Omission produces an explicitly
uncommitted review candidate; it must not be called a fixed-commit release.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = {"core", "hooks", "tests", "packages", "docs", "skills", "project-template", "global", "templates", "knowledge", ".github"}
ROOT_FILES = {"kit.py", "pyproject.toml", "README.md", "CHANGELOG.md", "LICENSE", "SMOKE_TEST.md", ".gitignore", ".gitattributes"}
EXTENSIONS = {".py", ".js", ".mjs", ".json", ".yaml", ".yml", ".md", ".toml", ".svg", ".txt"}


def allowed(name):
    p = Path(name)
    return ((len(p.parts) == 1 and name in ROOT_FILES)
            or (p.parts[0] in PREFIXES and p.suffix in EXTENSIONS
                and not any(c in {"__pycache__", "node_modules", ".agent", ".git", "runtime", ".test-runtime"} for c in p.parts)))


def build(output, commit=None):
    output.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    files = {}
    if commit:
        commit = subprocess.check_output(["git", "rev-parse", commit + "^{commit}"], cwd=ROOT, text=True).strip()
        archive = subprocess.check_output(["git", "archive", "--format=zip", commit], cwd=ROOT)
        with zipfile.ZipFile(io.BytesIO(archive)) as source:
            for name in source.namelist():
                if not name.endswith("/") and allowed(name):
                    files[name] = source.read(name)
    else:
        names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode("utf8").split("\0")
        for name in sorted(set(filter(None, names))):
            if allowed(name):
                path = ROOT / name
                if not path.resolve().is_relative_to(ROOT):
                    raise ValueError("Source path escapes repository: " + name)
                files[name] = path.read_bytes()
    if any(name not in files for name in ["kit.py", "core/__init__.py", "pyproject.toml", "docs/RELEASE_1_5_1.md"]):
        raise ValueError("Source candidate is incomplete")
    for name, data in files.items():
        if re.search(rb"sk-(?:proj-)?[A-Za-z0-9_-]{40,}", data):
            raise ValueError("Possible credential in source: " + name)
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    manifest = {"version": "1.5.1", "commit": commit, "base_commit": head,
                "status": "fixed-commit" if commit else "uncommitted-review-candidate", "files": hashes}
    files["SOURCE-MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    filename = "Project-Anchor-1.5.1" + ("" if commit else "-candidate") + "-source.zip"
    target = output / filename
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo("Project-Anchor-1.5.1/" + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, data)
    with zipfile.ZipFile(target) as bundle:
        if bundle.testzip() is not None or len(bundle.namelist()) != len(files):
            raise ValueError("ZIP integrity failed")
        for name, data in files.items():
            if bundle.read("Project-Anchor-1.5.1/" + name) != data:
                raise ValueError("ZIP roundtrip mismatch: " + name)
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(f"{checksum}  {filename}\n", encoding="utf8", newline="\n")
    result = {"archive": filename, "sha256": checksum, "files": len(files), "bytes": target.stat().st_size,
              "commit": commit, "base_commit": head, "status": manifest["status"], "roundtrip": "pass"}
    (output / "package-report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--commit")
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve(), args.commit), ensure_ascii=False))
