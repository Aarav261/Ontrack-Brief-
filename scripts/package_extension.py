"""Package the built extension into a ZIP for 'Load unpacked' distribution.

Run AFTER building the production bundle:

    cd extension && npm run build:prod
    python scripts/package_extension.py

Produces `ontracker.zip` at the repo root. The archive contains a
single top-level `ontracker/` folder — users unzip it and point
Chrome's "Load unpacked" at that folder.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIST = ROOT / "extension" / "dist"
OUT = ROOT / "ontracker.zip"
TOP = "ontracker"  # folder name inside the zip


def main() -> None:
    manifest_path = DIST / "manifest.json"
    if not manifest_path.exists():
        sys.exit(
            "extension/dist/manifest.json not found — run "
            "`cd extension && npm run build:prod` first."
        )

    files = [p for p in DIST.rglob("*") if p.is_file()]
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            arcname = f"{TOP}/{p.relative_to(DIST).as_posix()}"
            if p == manifest_path:
                # The Chrome Web Store assigns the extension ID on publish, so the
                # local `key` (which pins the ID for Load unpacked) is unnecessary
                # in the upload — strip it from the zip's manifest while leaving
                # dist/ untouched, so a load-unpacked build keeps its stable ID.
                manifest = json.loads(p.read_text(encoding="utf-8"))
                manifest.pop("key", None)
                z.writestr(arcname, json.dumps(manifest, indent=2) + "\n")
            else:
                z.write(p, arcname)

    size_kb = OUT.stat().st_size / 1024
    print(f"Wrote {OUT.name} ({size_kb:.0f} KB, {len(files)} files)")


if __name__ == "__main__":
    main()
