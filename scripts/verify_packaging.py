#!/usr/bin/env python3
"""Check that a built wheel actually installs and runs, outside the repo.

## Why this is a script and not a test

Everything in `tests/` runs against the *source tree*, with the repo's own
directory on `sys.path`. That is exactly the condition under which the
three failures this script exists to catch are invisible:

- **An undeclared dependency.** scipy is imported inside each fit
  function, which reads like a guard and is not one: it raises at the
  point of use rather than at import, so an install without it fitted
  nothing and only said so mid-run. The dev environment had it.
- **A file that is not in the wheel.** The model tables, the UI block
  configs, the workflow templates and their presets are data, and data is
  only packaged if the build backend was told to package it. The source
  tree has them either way.
- **An import that needs a particular working directory.** The desktop
  modules used to import each other flat (`from components.x import y`),
  which resolves only with `src/labpilot/ui/desktop` on `sys.path` —
  hence the `cd` that `launch.sh` used to need. From site-packages there
  is no such directory to be in.

So this builds a wheel, installs it into a throwaway venv, and drives it
from a directory that is not the repo. It needs the network the first
time (pip fetches the dependencies) and takes a couple of minutes.

    python scripts/verify_packaging.py           # core install
    python scripts/verify_packaging.py --gui     # also the desktop extra

The GUI half is opt-in because it pulls the whole Qt stack.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}" + (f" — {detail}" if not ok and detail else ""))
    if not ok:
        FAILED.append(label)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gui", action="store_true",
        help="also install the [app] extra and import the desktop modules",
    )
    parser.add_argument(
        "--keep", action="store_true", help="leave the temporary venv in place"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("LABPILOT PACKAGING VERIFICATION")
    print("=" * 70)

    work = Path(tempfile.mkdtemp(prefix="labpilot-pkg-"))
    dist = work / "dist"
    venv = work / "venv"
    # Run *from* the temp dir so a stray `import labpilot` cannot resolve
    # to the source tree — which would defeat the whole exercise.
    elsewhere = work

    try:
        print("\n1. Building the wheel and sdist")
        built = run([sys.executable, "-m", "build", "-o", str(dist)], cwd=ROOT)
        check("`python -m build` succeeds", built.returncode == 0,
              built.stderr.strip()[-400:])
        if built.returncode != 0:
            return 1
        wheels = list(dist.glob("*.whl"))
        sdists = list(dist.glob("*.tar.gz"))
        check("it produces one wheel", len(wheels) == 1, f"{[w.name for w in wheels]}")
        check("and one sdist", len(sdists) == 1, f"{[s.name for s in sdists]}")
        if not wheels:
            return 1
        wheel = wheels[0]

        print("\n2. The wheel carries its data files, not only its code")
        import zipfile

        names = set(zipfile.ZipFile(wheel).namelist())
        for needed in (
            "labpilot/instruments/NI/models.toml",
            "labpilot/instruments/OceanOptics/models.toml",
            "labpilot/ui/desktop/config/ui_blocks.toml",
            "labpilot/ui/desktop/config/workflow_blocks.toml",
            "labpilot/core/workflow_templates/presets.toml",
        ):
            check(needed.split("/", 1)[1], needed in names)
        check(
            "and the icon theme the Qt windows draw from",
            any(n.startswith("labpilot/ui/desktop/styles/icons/") for n in names),
        )
        # The browser UI, added by hatch_build.py when frontend/build exists.
        # Absent is a legitimate wheel — one built from a checkout that never
        # ran `npm run build` — so this warns rather than failing. A wheel for
        # release should have it, or `labpilot app` has no UI to serve without
        # a checkout to build one from.
        if "labpilot/frontend_build/index.html" in names:
            check(
                "and the built front end, with its assets and no source maps",
                any(n.startswith("labpilot/frontend_build/assets/") for n in names)
                and not any(n.endswith(".map") for n in names),
            )
        else:
            print(
                "  ⚠️  no bundled front end — run `npm run build` in frontend/ "
                "before building a release wheel"
            )

        print("\n3. Installing into a clean virtual environment")
        run([sys.executable, "-m", "venv", str(venv)])
        pip = venv / "bin" / "pip"
        python = venv / "bin" / "python"
        if not pip.exists():  # Windows
            pip, python = venv / "Scripts" / "pip.exe", venv / "Scripts" / "python.exe"

        spec = f"{wheel}[app]" if args.gui else str(wheel)
        print(f"   pip install {'(with [app], this pulls Qt)' if args.gui else ''} …")
        installed = run([str(pip), "install", "-q", spec])
        check("pip install succeeds", installed.returncode == 0,
              installed.stderr.strip()[-400:])
        if installed.returncode != 0:
            return 1

        print("\n4. It works from a directory that is not the repo")
        probe = (
            "import labpilot, pathlib;"
            "assert 'site-packages' in labpilot.__file__, labpilot.__file__;"
            "from labpilot.instruments import adapter_registry;"
            "from labpilot.instruments.NI.models import load_models;"
            "from labpilot.core.workflow.presets import load_presets;"
            "print(len(adapter_registry.list()), len(load_models()), len(load_presets()))"
        )
        out = run([str(python), "-c", probe], cwd=elsewhere)
        check("imports resolve to the installed package", out.returncode == 0,
              out.stderr.strip()[-400:])
        if out.returncode == 0:
            adapters, models, presets = (int(v) for v in out.stdout.split())
            # A floor, not the full count. Neither install here brings the
            # driver extras, and the ~240 pymeasure and pylablib stubs
            # register only when their library is importable — which is the
            # point of them being extras. So this is the mocks plus the
            # hand-written adapters: 67 today, 307 with both extras.
            check(
                "the adapter registry is populated",
                adapters > 50,
                f"only {adapters} registered",
            )
            check("the NI model table loads", models > 40, f"{models}")
            check("the workflow presets load", presets > 0, f"{presets}")

        print("\n5. Every declared dependency is really declared")
        # The one that was missing: fits are imported lazily, so a bare
        # install used to raise ModuleNotFoundError at fit time.
        fit = run([str(python), "-c",
                   "import numpy as np;"
                   "from labpilot.core.analysis.fits import fit_dip;"
                   "x=np.linspace(2.8e9,2.9e9,201);"
                   "y=1-0.3/(1+((x-2.87e9)/3e6)**2);"
                   "print(round(fit_dip(x,y)['center']/1e9, 4))"], cwd=elsewhere)
        check("a fit runs without an extra installed", fit.returncode == 0,
              fit.stderr.strip()[-300:])
        if fit.returncode == 0:
            check("and finds the right centre", fit.stdout.strip() == "2.87",
                  fit.stdout.strip())

        print("\n6. The console scripts exist and run")
        for script, flag in (("labpilot", "--help"), ("labpilot", "list-adapters")):
            exe = venv / "bin" / script
            if not exe.exists():
                exe = venv / "Scripts" / f"{script}.exe"
            result = run([str(exe), flag], cwd=elsewhere)
            check(f"`{script} {flag}`", result.returncode == 0,
                  result.stderr.strip()[-300:])

        if args.gui:
            print("\n7. The desktop modules import with no repo and no cwd")
            gui_probe = (
                "import labpilot.ui.desktop.manager_qt_webview;"
                "import labpilot.ui.desktop.main;"
                "import labpilot.ui.desktop.workflow_window;"
                "import labpilot.ui.desktop.instrument_window;"
                "import labpilot.ui.desktop.components.pulse_editor;"
                "print('ok')"
            )
            env = {"QT_QPA_PLATFORM": "offscreen", "PATH": "/usr/bin:/bin"}
            gui = run([str(python), "-c", gui_probe], cwd=elsewhere, env=env)
            check("they import from site-packages", gui.returncode == 0,
                  gui.stderr.strip()[-500:])
            manager = venv / "bin" / "labpilot-manager"
            check("`labpilot-manager` is installed", manager.exists())
    finally:
        if args.keep:
            print(f"\n(kept {work})")
        else:
            shutil.rmtree(work, ignore_errors=True)

    print("\n" + "=" * 70)
    if FAILED:
        print(f"{len(FAILED)} packaging check(s) FAILED:")
        for name in FAILED:
            print(f"  - {name}")
        return 1
    print("The built wheel installs and runs standalone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
