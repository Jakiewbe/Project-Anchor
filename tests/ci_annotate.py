"""Run the regression and surface failures as GitHub annotations.

Job logs on a public repository need authentication, but check-run annotations
do not. Every failing test becomes one annotation, and the first traceback is
summarised (exception line plus frame locations) so a red build stays
diagnosable without a token.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURE = re.compile(r"^(FAIL|ERROR): ")
SEPARATOR = re.compile(r"^(={5,}|-{5,})$")
FRAME = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')


def blocks(lines):
    """Split unittest -v output into (header, body) pairs for failing tests."""
    result = []
    index = 0
    while index < len(lines):
        if FAILURE.match(lines[index]):
            header = lines[index]
            body = []
            index += 1
            while index < len(lines) and not FAILURE.match(lines[index]):
                line = lines[index]
                if re.match(r"^={5,}$", line) or line.startswith("Ran ") or line in ("OK", "FAILED"):
                    break
                if not SEPARATOR.match(line) and line.strip():
                    body.append(line)
                index += 1
            result.append((header, body))
        else:
            index += 1
    return result


def summarise(header, body):
    message = body[-1].strip() if body else "无异常信息"
    frames = [f"{Path(path).name}:{number} {name}" for path, number, name in
              (FRAME.match(line.strip()).groups() for line in body if FRAME.match(line.strip()))]
    return re.sub(r"\s+", " ", f"{header} :: {message} :: {'; '.join(frames[:3])}")[:900]


def main():
    result = subprocess.run([sys.executable, "-X", "utf8", "-m", "unittest",
                             "discover", "-s", "tests", "-v"],
                            cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    lines = (result.stdout + result.stderr).splitlines()
    log = ROOT / ".agent/runtime/ci-tests.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(result.stdout + result.stderr, encoding="utf-8", newline="\n")
    print("\n".join(line for line in lines
                    if FAILURE.match(line) or line.startswith(("Ran ", "FAILED", "OK"))))
    skipped = sum("... skipped " in line for line in lines)
    print(f"Skipped: {skipped}")
    if not result.returncode:
        return 0
    for header, body in blocks(lines)[:20]:
        print("::error::" + summarise(header, body))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
