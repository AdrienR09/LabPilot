"""What produced a run — captured once per process.

`RunMeta` already records the device schemas and the plan parameters, which
says what the instruments were and how they were asked to behave. It did
not say which *program* did the asking, and that is the one piece of
provenance you cannot reconstruct afterwards: the schemas are still in the
file, but the code has moved on. A year later you have the numbers and the
settings and no way to say which version produced them.

Everything here is best-effort and cached for the life of the process. A
missing git binary, a wheel install with no repository, an environment with
no `USER` — each leaves its key out rather than raising or guessing, on the
same rule the rest of this codebase follows: a field nobody was sure of is
absent, and an absent field is never validated.
"""

from __future__ import annotations

import getpass
import os
import platform
import socket
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

__all__ = ["software"]

#: Where to look for a repository: the installed package's parent tree. A
#: wheel install has no `.git` above it, which is exactly how we tell the
#: two cases apart.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("labpilot")
    except PackageNotFoundError:
        return ""


def _git() -> dict[str, str]:
    """The checkout's commit, and whether it had uncommitted changes.

    The `dirty` flag matters more than the sha: a sha alone implies the
    file can be reproduced, which is false the moment someone edited a
    template and ran it without committing. Saying so is the difference
    between provenance and a reassuring-looking string.
    """
    root = _PACKAGE_ROOT.parent.parent  # src/labpilot -> src -> <repo>
    if not (root / ".git").exists():
        return {}
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=5, check=False,
        )
        if sha.returncode != 0:
            return {}
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root, capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}

    info = {"git_sha": sha.stdout.strip()}
    if status.returncode == 0 and status.stdout.strip():
        info["git_dirty"] = "true"
    return info


def _user() -> str:
    # getpass consults several environment variables and then the password
    # database; on a service account with none of them it raises rather
    # than returning a placeholder.
    try:
        return getpass.getuser()
    except (OSError, KeyError, ImportError):
        return os.environ.get("USER") or os.environ.get("USERNAME") or ""


@lru_cache(maxsize=1)
def software() -> dict[str, str]:
    """Which program is taking this data.

    Cached: the git subprocesses run at most once per process, on the
    first run rather than at import, so a backend that never acquires
    anything never pays for them.
    """
    found = {
        "labpilot": _version(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "host": socket.gethostname(),
        "user": _user(),
        "executable": sys.executable,
        **_git(),
    }
    return {key: value for key, value in found.items() if value}
