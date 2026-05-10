"""Cron job installation for the morning brief."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def setup_cron(hour: int = 8, minute: int = 0) -> None:
    script  = Path(__file__).resolve().parent / "brief.py"
    python  = sys.executable
    log     = script.parent.parent / "brief.log"
    marker  = "# ontrack-morning-brief"
    entry   = f"{minute} {hour} * * 1-5 {python} {script} >> {log} 2>&1  {marker}"

    result   = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""

    lines    = [l for l in existing.splitlines() if "ontrack-morning-brief" not in l]
    lines.append(entry)
    new_cron = "\n".join(lines) + "\n"

    subprocess.run(["crontab", "-"], input=new_cron, text=True, check=True)
    print(f"✓ Scheduled: weekdays at {hour:02d}:{minute:02d}")
    print(f"  Logs  → {log}")
    print(f"  Remove with: crontab -e  (delete the ontrack-morning-brief line)")
