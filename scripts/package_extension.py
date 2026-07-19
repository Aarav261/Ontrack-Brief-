"""Package the built extension into a ZIP for 'Load unpacked' distribution.

Run AFTER building the production bundle:

    cd extension && npm run build:prod
    python scripts/package_extension.py

Produces `ontracker.zip` at the repo root, with manifest.json at the ARCHIVE
ROOT rather than inside a nested folder. Unzipping gives a single `ontracker/`
folder (named by the archive) holding the manifest directly, which is what
Chrome's "Load unpacked" expects. Nesting a folder inside made the extracted
tree `ontracker/ontracker/`, so pointing Chrome at the obvious outer folder
failed with "Manifest file is missing or unreadable". Root layout is also what
the Chrome Web Store requires for an upload.

The manifest `key` is KEPT by default, and that is load-bearing: it pins the
extension ID to gkbemcnnekeadcpikdcfhedifdglihbn, which is the only
chrome-extension:// origin in Clerk's allowed_origins (see
scripts/clerk_set_allowed_origins.py). Ship a zip without it and every user
gets a random ID that Clerk rejects, so sign-in fails and setup can never
complete. Pass --webstore to strip it for a Store upload, where Google assigns
the ID instead.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIST = ROOT / "extension" / "dist"
OUT = ROOT / "ontracker.zip"


def main(webstore: bool = False) -> None:
    manifest_path = DIST / "manifest.json"
    if not manifest_path.exists():
        sys.exit(
            "extension/dist/manifest.json not found — run "
            "`cd extension && npm run build:prod` first."
        )

    files = [p for p in DIST.rglob("*") if p.is_file()]
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            arcname = p.relative_to(DIST).as_posix()
            if p == manifest_path and webstore:
                # Only for a Web Store upload: Google assigns the extension ID on
                # publish and rejects a manifest that pins one, so drop `key`.
                # NEVER for the load-unpacked zip — see the warning in main().
                manifest = json.loads(p.read_text(encoding="utf-8"))
                manifest.pop("key", None)
                z.writestr(arcname, json.dumps(manifest, indent=2) + "\n")
            else:
                z.write(p, arcname)

    size_kb = OUT.stat().st_size / 1024
    kind = "Web Store upload" if webstore else "Load unpacked"
    print(f"Wrote {OUT.name} ({size_kb:.0f} KB, {len(files)} files) — for {kind}")
    if webstore:
        print(
            "WARNING: `key` stripped, so this build gets a Store-assigned ID. Do "
            "NOT hand this to users for Load unpacked — Clerk only allowlists the "
            "keyed ID, and sign-in fails from any other origin."
        )


if __name__ == "__main__":
    main(webstore="--webstore" in sys.argv)
