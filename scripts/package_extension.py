"""Package the built extension into a ZIP for 'Load unpacked' distribution.

Run AFTER building the production bundle:

    cd extension && npm run build:prod
    python scripts/package_extension.py

Produces `ontrack-brief-extension.zip` at the repo root. The archive contains a
single top-level `ontrack-brief-extension/` folder — users unzip it and point
Chrome's "Load unpacked" at that folder.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIST = ROOT / "extension" / "dist"
OUT = ROOT / "ontrack-brief-extension.zip"
TOP = "ontrack-brief-extension"  # folder name inside the zip


def main() -> None:
    if not (DIST / "manifest.json").exists():
        sys.exit(
            "extension/dist/manifest.json not found — run "
            "`cd extension && npm run build:prod` first."
        )

    files = [p for p in DIST.rglob("*") if p.is_file()]
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, f"{TOP}/{p.relative_to(DIST).as_posix()}")

    size_kb = OUT.stat().st_size / 1024
    print(f"Wrote {OUT.name} ({size_kb:.0f} KB, {len(files)} files)")


if __name__ == "__main__":
    main()
