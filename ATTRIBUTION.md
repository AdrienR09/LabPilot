# Attribution, provenance and licensing

LabPilot exists because Qudi and PyMoDAQ exist. It is not an attempt to
replace either. It is an attempt to take what each of them got right —
Qudi's instrument interfaces and measurement logic, PyMoDAQ's plugin
discovery, data model and plotting widgets — and combine them into one
framework that is more modular and easier to script than either is on its
own.

This document records, precisely, what comes from where, so that credit is
given accurately and so that anyone redistributing this project knows what
they are redistributing.

---

## 1. How this project was developed

**LabPilot's implementation is AI-assisted.** A large fraction of the code
in this repository was written by a large language model (Anthropic's
Claude) working from the upstream projects as references, under the
direction and review of the maintainer.

The working method was, throughout:

1. Read the relevant upstream implementation — usually Qudi's, sometimes
   PyMoDAQ's — closely enough to understand not just what it does but why
   it does it that way, including the failure modes its structure is
   defending against.
2. Write a fresh implementation for this framework's own architecture.
3. Cite the upstream file that the design came from, in the docstring of
   the module that reimplements it.

Those citations are real and are spread through the source — 36 modules
under `src/` reference Qudi by name, usually with the exact upstream file
path. They are there so that a reader can check the derivation, and so
that the debt is visible in the code rather than only in this file.

Two consequences worth stating plainly, because AI-assisted code has
specific characteristic risks:

- **The upstream projects are the authority, not this one.** Where
  LabPilot's behaviour disagrees with Qudi's or PyMoDAQ's on a point of
  physics or instrument control, assume LabPilot is wrong until shown
  otherwise.
- **Hardware-facing code is the least verified part.** Everything here is
  tested against mocks and simulated devices. Adapters marked as untested
  against real hardware are exactly that, and the docstrings say so.

## 2. What is derived from Qudi

Qudi (Ulm University, Institute for Quantum Optics) is the single largest
influence on this framework's design.

Derived from Qudi as **design**, reimplemented rather than copied:

| Here | From |
|---|---|
| `instruments/hardware_scan_mixin.py` | `interface/scanning_probe_interface.py`, `hardware/ni_x_series/`, `hardware/interfuse/ni_scanning_probe_interfuse.py` |
| `core/run/plans.py` — scan, optimize | `logic/scanning_probe_logic.py`, `logic/scanning_optimize_logic.py` |
| `core/device/constraints.py` | `util/constraints.py`, `interface/fast_counter_interface.py`'s set-and-confirm convention |
| `instruments/mock/microwave_sources.py` | `interface/microwave_interface.py` |
| `instruments/mock/pulse_sequencers.py` | `interface/pulser_interface.py` |
| `ui/desktop/components/workflow_result.py` | `gui/scanning/`, `util/widgets/plotting/` |
| `ui/desktop/components/odmr_control.py` | `gui/odmr/` |
| N-D scanning and optimiser-by-decomposition | `ScanningOptimizeLogic`'s sub-scan sequence, generalised past its 2-D ceiling |

**No Qudi source code is copied into this project's Python.** The
derivation is at the level of interfaces, method contracts, data flow and
the reasoning behind them. This distinction matters legally: Qudi's
pulsed and logic modules are GPL-3.0 (legacy tree) and LGPL-3.0
(`qudi-iqo-modules`), neither of which permits verbatim inclusion in an
MIT-licensed work. Interfaces and ideas are not restricted by copyright;
source text is.

Where Qudi's *artwork* is used, it is used as artwork, kept in its own
files with its own licence text retained:

| Asset | Licence |
|---|---|
| `ui/desktop/styles/icons/` — Oxygen icon theme | LGPL, see `icons/LICENSE.txt` |
| `ui/desktop/styles/icons/` — Qudi specialty icons | LGPL, see `icons/LICENSE-qudiTheme.txt` |
| `ui/desktop/styles/qdark.qss`, `qdark_assets/` | MIT (QDarkStyleSheet, © Colin Duquesnoy) — see `qdark_assets/LICENSE.txt` |
| `ui/desktop/styles/dracula.qss`, `qtdark.qss` | **GPL-3.0, from qudi-legacy — see §5** |

## 3. What is used from PyMoDAQ

PyMoDAQ (CEMES-CNRS, Toulouse; Sébastien Weber) is **MIT-licensed**, so
unlike Qudi it can be used directly, and it is:

- `pymodaq_gui.plotting.data_viewers` — `Viewer0D`/`1D`/`2D`/`ND` are used
  as the actual plotting widgets in `ui/desktop/components/viewer.py` and
  `time_series.py`. These are genuinely good and there was no reason to
  rewrite them.
- `pymodaq_data.data` — `Axis`/`DataRaw` as the payload handed to those
  viewers.

Derived from PyMoDAQ as **design**:

- Entry-point plugin discovery (`labpilot.adapters`) follows PyMoDAQ's
  `pymodaq.instruments` / `pymodaq.extensions` mechanism.
- `core/data/dataset.py`'s separation of axes from values follows
  `DataWithAxes`, with navigation/signal dimensions playing a similar
  role to `nav_indexes`/`sig_indexes`.
- The config-driven UI in `ui_blocks.toml` is a more literal, file-based
  form of what PyMoDAQ does with parameter trees.

The pulsed-measurement design work also studied
`Montpellier-S2QT/pymodaq_plugins_pulsedmeasurement` (MIT), whose
practical structure for NV pulsed ODMR informed this project's plan.

## 4. Other upstream projects

- **PyMeasure** (MIT) — 188 of the 301 catalogued adapters are generated
  from PyMeasure's own instrument classes; PyMeasure is an optional
  runtime dependency and the instruments remain its work.
- **pylablib** (BSD) — backs 55 catalogued adapters, likewise as an
  optional dependency.
- **QDarkStyleSheet** (MIT, © Colin Duquesnoy) — the default theme.
- **Oxygen Icon Theme** (LGPL) — the icon set.

## 5. Known licensing issue

Two files are vendored verbatim from qudi-legacy and are **GPL-3.0**:

    src/labpilot/ui/desktop/styles/dracula.qss
    src/labpilot/ui/desktop/styles/qtdark.qss

GPL-3.0 content cannot be redistributed inside an MIT-licensed work. These
are two optional cosmetic themes and nothing depends on them: the default
theme (`qdark.qss`) and its assets are separately MIT-licensed within Qudi
and are not affected.

**This must be resolved before any public release.** The options, in
rough order of least disruption:

1. Delete both files and their entries in `main.py`'s `THEMES`.
2. Replace them with independently MIT/BSD-licensed equivalents.
3. Relicense this project as GPL-3.0, which would also change what can be
   done with everything else here.

Until one of those is done, this repository should be treated as **not
cleanly MIT-licensed as a whole**, and the `LICENSE` file's blanket claim
does not hold for those two files.

## 6. Summary of the licence position

| Component | Licence | Status |
|---|---|---|
| LabPilot's own Python source | MIT | Clean |
| Design derived from Qudi | — | Ideas and interfaces; not copyrightable, cited in source |
| PyMoDAQ packages | MIT | Used as dependencies, compatible |
| PyMeasure, pylablib | MIT / BSD | Optional dependencies, compatible |
| Oxygen + Qudi icons | LGPL | Kept as separate files with licence text retained |
| `qdark.qss` + assets | MIT | Licence text retained |
| `dracula.qss`, `qtdark.qss` | GPL-3.0 | **Incompatible — see §5** |

## 7. If you are one of these projects' maintainers

If anything here misrepresents your work, under-credits it, or uses it in
a way you did not intend, that is a bug and will be fixed. Please open an
issue. The intent of this project is to build on your work and say so
clearly, not to obscure where it came from.
