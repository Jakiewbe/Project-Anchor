"""Run the regression and surface failures as GitHub annotations.

Job logs need authentication, but check-run annotations are public. This keeps
a red build diagnosable without anyone extracting a token: every failing test
becomes one annotation, and the first traceback is summarised in another.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURE = re.compile(r"^(FAIL|ERROR): ")


def main():
    result = subprocess.run([sys.executable, "-X", "utf8", "-m", "unittest",
                             "discover", "-s", "tests", "-v"],
                            cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    output = (result.stdout + result.stderr).splitlines()
    summary = [line for line in output
               if FAILURE.match(line) or line.startswith("Ran ") or line in ("OK", "FAILED")]
    print("\n".join(summary))
    if not result.returncode:
        return 0
    failures = [line for line in output if FAILURE.match(line)]
    for line in failures[:20]:
        print(f"::error::{line}")
    first = next((index for index, line in enumerate(output) if FAILURE.match(line)), None)
    if first is not None:
        block = []
        for line in output[first + 1:]:
            if FAILURE.match(line) or re.match(r"^-{10,}$", line.strip()) or line.startswith("Ran "):
                break
            if line.strip():
                block.append(line.strip())
        if block:
            print("::error::第一个失败: " + block[-1][:900])
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
