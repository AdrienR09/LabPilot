"""Put the built React front end into the wheel, when there is one.

A plain `[tool.hatch.build.targets.wheel.force-include]` cannot express
this: hatchling raises `FileNotFoundError: Forced include not found` when
the path is missing, so declaring `frontend/build` there would break
`pip install .` and `pip install -e .` on every fresh clone — the bundle is
a build artifact, it is gitignored, and a clone has none until `npm run
build` has run.

A hook can look first. With a bundle present the wheel carries it at
`labpilot/frontend_build/`, which is the first place `core/frontend.py`
looks, so `pip install labpilot` gives a working browser UI with no Node
installed anywhere. With none, the wheel is exactly what it was before and
`labpilot app` builds or serves the front end from a checkout instead.

Deliberately does NOT run `npm run build` itself. pip builds a wheel from
an sdist on the user's machine, and requiring Node there would turn a
missing front end from a degraded install into a failed one.
"""

from __future__ import annotations

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# Source maps are roughly four times the bundle they describe and are only
# useful to someone debugging the front end, who has the checkout anyway.
EXCLUDED_SUFFIXES = {".map"}


class FrontendBuildHook(BuildHookInterface):
    PLUGIN_NAME = "frontend"

    def initialize(self, version: str, build_data: dict) -> None:
        build_dir = Path(self.root) / "frontend" / "build"
        if not (build_dir / "index.html").is_file():
            # A warning, not an error: a wheel without the browser UI is
            # still a working framework, server and CLI.
            print(
                "WARNING: no built front end at frontend/build — this wheel will "
                "have no browser UI. Run `npm run build` in frontend/ first."
            )
            return

        forced = build_data["force_include"]
        included = 0
        for path in sorted(build_dir.rglob("*")):
            if not path.is_file() or path.suffix in EXCLUDED_SUFFIXES:
                continue
            target = path.relative_to(build_dir).as_posix()
            forced[str(path)] = f"labpilot/frontend_build/{target}"
            included += 1
        print(f"Bundling the front end into the wheel ({included} files)")
