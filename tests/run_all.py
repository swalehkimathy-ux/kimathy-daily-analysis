"""Endesha majaribio yote ya KIMATHY SMART BETTING ENGINE (offline, hakuna mtandao)."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = ["test_clock.py", "test_normalize.py", "test_validate.py", "test_analyze.py",
         "test_candidates.py", "test_optimize.py", "test_tipsters.py", "test_end_to_end.py"]


def main() -> int:
    print("=" * 74)
    print("  KIMATHY SMART BETTING ENGINE — MAJARIBIO YOTE (offline)")
    print("=" * 74)
    passed, failed = [], []
    for t in TESTS:
        t0 = time.monotonic()
        r = subprocess.run([sys.executable, str(HERE / t)], cwd=str(HERE.parent),
                           capture_output=True, text=True, timeout=600)
        dt = time.monotonic() - t0
        ok = r.returncode == 0
        (passed if ok else failed).append(t)
        tail = (r.stdout or "").strip().splitlines()
        line = tail[-1] if tail else ""
        print(f"\n{'✓' if ok else '✗'} {t}  ({dt:.2f}s)")
        if line:
            print(f"    {line}")
        if not ok:
            err = (r.stderr or r.stdout or "").strip().splitlines()
            for l in err[-14:]:
                print(f"    | {l}")
    print("\n" + "=" * 74)
    print(f"  YALIYOPITA: {len(passed)}/{len(TESTS)}"
          + (f"  ·  YALIYOSHINDWA: {', '.join(failed)}" if failed else "  ·  YOTE GREEN"))
    print("=" * 74)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
