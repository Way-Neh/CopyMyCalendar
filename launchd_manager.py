"""
launchd_manager.py - Manages macOS background service using launchd.
"""

import os
import subprocess
import plistlib
from pathlib import Path
from typing import Dict, Any

PLIST_LABEL = "com.sendtogmail.calendar-sync"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PATH = LAUNCH_AGENTS_DIR / f"{PLIST_LABEL}.plist"


class LaunchdManager:
    """Helper to install, start, stop, and inspect the macOS launchd agent."""

    def __init__(self, project_dir: str, python_path: str, interval_minutes: int = 15):
        self.project_dir = os.path.abspath(project_dir)
        self.python_path = os.path.abspath(python_path)
        self.interval_seconds = max(60, interval_minutes * 60)
        self.wrapper_script = os.path.join(self.project_dir, "run_sync.sh")
        self.stdout_log = os.path.join(self.project_dir, "sync.log")
        self.stderr_log = os.path.join(self.project_dir, "sync.error.log")

    def generate_plist_dict(self) -> Dict[str, Any]:
        """Generate launchd plist configuration dictionary."""
        return {
            "Label": PLIST_LABEL,
            "ProgramArguments": [
                "/bin/zsh",
                self.wrapper_script,
                "sync"
            ],
            "WorkingDirectory": self.project_dir,
            "StartInterval": self.interval_seconds,
            "RunAtLoad": True,
            "StandardOutPath": self.stdout_log,
            "StandardErrorPath": self.stderr_log,
            "ProcessType": "Background",
            "EnvironmentVariables": {
                "LANG": "en_US.UTF-8",
                "LC_ALL": "en_US.UTF-8",
                "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
            }
        }

    def install(self) -> str:
        """Create and load the launchd agent."""
        LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)

        if PLIST_PATH.exists():
            self.uninstall()

        plist_data = self.generate_plist_dict()
        with open(PLIST_PATH, "wb") as f:
            plistlib.dump(plist_data, f)

        # Load service into launchctl
        try:
            # Modern launchctl bootstrap
            uid = os.getuid()
            subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(PLIST_PATH)], check=True, stderr=subprocess.DEVNULL)
        except Exception:
            # Fallback for older macOS
            subprocess.run(["launchctl", "load", "-w", str(PLIST_PATH)], check=True)

        return str(PLIST_PATH)

    def uninstall(self) -> bool:
        """Unload and remove the launchd agent."""
        if PLIST_PATH.exists():
            uid = os.getuid()
            try:
                subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(PLIST_PATH)], stderr=subprocess.DEVNULL)
            except Exception:
                try:
                    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], stderr=subprocess.DEVNULL)
                except Exception:
                    pass
            PLIST_PATH.unlink(missing_ok=True)
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        """Check if service is loaded and running."""
        is_installed = PLIST_PATH.exists()
        is_loaded = False
        pid = None

        if is_installed:
            try:
                res = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=True)
                for line in res.stdout.splitlines():
                    if PLIST_LABEL in line:
                        parts = line.split()
                        is_loaded = True
                        if len(parts) > 0 and parts[0].isdigit():
                            pid = int(parts[0])
                        break
            except Exception:
                pass

        return {
            "installed": is_installed,
            "loaded": is_loaded,
            "pid": pid,
            "plist_path": str(PLIST_PATH),
            "log_path": self.stdout_log,
            "error_log_path": self.stderr_log,
        }
