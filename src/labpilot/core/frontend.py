"""Where the React front end is, independent of the current directory.

The server used to look for `frontend/build` relative to the process's
working directory, which meant `labpilot start` served the browser UI
only when launched from a repo root and served *nothing* — silently,
with no log line — from anywhere else. That is the normal case for an
installed package, so the front end was effectively unreachable unless
you also ran the Vite dev server.

Both directories are resolved the same way, in the same order, so
`labpilot app` and the server always agree about which front end is in
play:

1. `$LABPILOT_FRONTEND` / `$LABPILOT_FRONTEND_SRC`, for a build living
   somewhere neither of the two layouts below covers.
2. Inside the installed package, where the wheel puts the built bundle.
3. A checkout, three levels up from this file.
4. Relative to the working directory — what the server did before, kept
   so a `cd`-into-the-repo habit keeps working.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "BUILD_ENV_VAR",
    "SOURCE_ENV_VAR",
    "frontend_build_dir",
    "frontend_source_dir",
]

BUILD_ENV_VAR = "LABPILOT_FRONTEND"
SOURCE_ENV_VAR = "LABPILOT_FRONTEND_SRC"

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
# .../<repo>/src/labpilot/core/frontend.py -> .../<repo>
_CHECKOUT_ROOT = Path(__file__).resolve().parents[3]


def _candidates(env_var: str, packaged: str, checkout: tuple[str, ...]) -> Iterator[Path]:
    override = os.environ.get(env_var)
    if override:
        yield Path(override).expanduser()
    yield _PACKAGE_ROOT / packaged
    yield _CHECKOUT_ROOT.joinpath(*checkout)
    yield Path(*checkout)


def frontend_build_dir() -> Path | None:
    """The directory holding a built `index.html`, or None if none exists.

    Identified by the built entry point rather than by the directory
    existing: an interrupted or never-run `npm run build` leaves an empty
    `frontend/build`, and serving that is worse than reporting no front
    end at all.
    """
    for candidate in _candidates(BUILD_ENV_VAR, "frontend_build", ("frontend", "build")):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def frontend_source_dir() -> Path | None:
    """The directory holding `package.json`, or None — i.e. whether this
    install can run the Vite dev server or build the bundle itself.

    Absent from a wheel by design; only a checkout has it.
    """
    for candidate in _candidates(SOURCE_ENV_VAR, "frontend", ("frontend",)):
        if (candidate / "package.json").is_file():
            return candidate
    return None
