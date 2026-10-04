# Bringing LabPilot up on a lab PC

Written for the person standing at the rig. It assumes nothing is installed
and ends with a table saying which instruments agree with the schemas
LabPilot declares for them.

Read it in order. Each step is cheap to repeat and nothing before step 5
touches hardware.

---

## 1. Install Python and LabPilot

LabPilot needs **Python 3.11 or newer**. On Windows, install it from
[python.org](https://www.python.org/downloads/windows/) and tick *Add
python.exe to PATH*.

```powershell
git clone https://github.com/AdrienR09/LabPilot
cd LabPilot
python -m pip install -e ".[lab]"
```

`[lab]` is the desktop app plus every instrument driver that comes from
PyPI: `pymeasure`, `pylablib`, `nidaqmx`, `nifpga`, `seabreeze`,
`pulsestreamer`, `spinapi`. On a machine that is about to be wired to
instruments, having all of them is the point — `[app]` alone gets you the
GUI and the mocks.

> **`pip install -e . --no-deps` installs nothing.** If the app starts and
> then complains about PyQt or pyqtgraph, this is why.

The front end needs no setting up. An installed wheel carries the built
bundle, and from a checkout `labpilot app` runs `npm install` and
`npm run build` itself the first time. That first launch needs
[Node](https://nodejs.org/) on PATH; after it, nothing does.

## 2. Check it runs with no hardware at all

```powershell
labpilot rig-init mock_rig
labpilot app
```

`mock_rig` is a complete simulated setup — stage, APD, spectrometer,
microwave source, pulser, gated counter. Everything in LabPilot works
against it: a 2-D scan, an ODMR sweep, a Rabi. **Do this before touching an
instrument**, so that when something does not work later you already know
it is the hardware and not the install.

If the window does not appear but the terminal says uvicorn is running, use
`labpilot app --no-window` and open the URL it prints. The Qt window needs
`PyQt6-WebEngine`, which `[app]` installs and `--no-deps` does not.

### If a port cannot be bound on Windows

```
error while attempting to bind on address ('0.0.0.0', 8000):
an attempt was made to access a socket in a way forbidden by its access permissions
```

That is `WinError 10013`, and it almost never means something is listening.
Hyper-V, WSL2 and Docker Desktop reserve blocks of TCP ports at boot, and a
bind inside one fails while every "is this port free?" check says it is
free. Look at the reservations with:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

`labpilot app` already handles this — it *binds* to test a port rather than
connecting, and picks another when the preferred one is unavailable. Only
`labpilot start --port` needs choosing by hand.

## 3. Install the vendor drivers

Six of the instruments here have no PyPI package at all. Their libraries
arrive with the manufacturer's own installer, and LabPilot loads them at
**connect** time — so everything below is catalogued, describable and
probeable with `--offline` before any of it is installed.

| Instrument | What to install | What LabPilot loads |
|---|---|---|
| PicoHarp 300 | PicoQuant's PicoHarp software | `phlib64.dll` |
| Mad City Labs Nano-Drive | MCL's Nano-Drive installer | `Madlib.dll` |
| Mad City Labs Micro-Drive | MCL's Micro-Drive installer | `MicroDrive.dll` |
| SPAD512 | Pi Imaging's application | `SPAD512S.py`, **and the app must be running** |
| Hamamatsu camera | Hamamatsu DCAM-API | via `pylablib` |
| Andor EMCCD | Andor SDK2 | via `pylablib` |
| NI PXI card | NI-DAQmx | via `nidaqmx` |
| NI R-Series FPGA | NI-RIO, **plus a bitfile you compile** | via `nifpga` |

Two that need nothing: the **Siglent microwave source** speaks SCPI over a
plain socket, so its IP address is the whole configuration; the **NKT
SuperK** speaks Interbus over a serial port through `pylablib`, which
`[lab]` already installed.

The **SPAD512 is unusual**: Pi Imaging's own application owns the camera and
serves a TCP port on `127.0.0.1`. LabPilot is a client of that port, so
their software has to be running, and the camera cannot be shared with
their live view during a measurement.

## 4. Declare your rig

```powershell
labpilot rig-templates
labpilot rig-init nv_confocal
```

That writes `~/.labpilot/config/instruments/nv_confocal.cfg` — the same file
the Devices tab would have produced, with the right adapter for each
instrument and sensible ids (`stage_fine`, `counter`, `mw`) that workflows
bind to. It prints what is still unknown:

```
mw.host — the IP address the Siglent's LAN screen shows
daq.model — the NI card's model, e.g. PXIe-6363
daq.channels — which terminal each signal is on, e.g. 'x=ao0, y=ao1, apd=ctr0/pfi8'
```

Fill those in the Devices tab or in the file. `labpilot rig-init
spad_imaging` does the same for the second setup; they are separate configs
and you switch between them.

For the NI card, `python scripts/ni_probe.py` run on the machine with the
card in it prints the model and its real channel inventory.

## 5. Probe everything

```powershell
labpilot probe --all
```

This is the first thing that touches hardware, and it is deliberately the
smallest thing that can: for each instrument it connects, prints the schema
LabPilot declares, prints it again once the device has answered, reads
**once**, and reports every disagreement. **It writes nothing and moves
nothing** — no setter, no action, no staging. That is what makes it safe to
run with a sample under the objective.

```
── nv_confocal: 8 instruments ──
   ✓ agrees      stage_fine    mcl_nano_drive
   ✗ disagrees   counter       picoharp_300
   · unreachable  mw           siglent_ssg
```

- **✓ agrees** — the hardware matches what LabPilot says about it.
- **✗ disagrees** — the schema is wrong and the output says how: a
  parameter declared readable that never came back, a pixel count that is
  not what the model table says, a position outside its own declared
  travel. Worth reporting; the hardware is right.
- **· unreachable** — a missing driver, a wrong address, or the instrument
  is off. The message distinguishes those.

`labpilot probe <adapter> --offline` prints what an adapter claims without
connecting to anything, which is useful on a laptop. One instrument at a
time:

```powershell
labpilot probe siglent_ssg --param host=192.168.1.42
labpilot probe mcl_nano_drive
labpilot probe picoharp_300 --json
```

Exit codes are meant for a shell: 0 agreement, 1 a disagreement, 2 could
not tell. So a lab machine can keep the shipped schemas honest in CI.

### What a first probe is expected to find

**Every adapter for the instruments on these two rigs has been written
against the vendor's documentation and never run against the instrument.**
A first probe finding something is normal. These in particular are what it
is for:

| Instrument | What the probe settles |
|---|---|
| Siglent | The real frequency and power range, read from the instrument. **An SSG3021X stops at 2.1 GHz and cannot reach the 2.87 GHz NV resonance at all** — better to find that out here. |
| Nano-Drive | Axis count and travel per axis, both read from the stage. |
| Micro-Drive | Axis count, and whether the limit-switch bits are the way round the adapter assumes. |
| PicoHarp | Base resolution and the bin-width ladder. |
| Hamamatsu | Sensor size, and that a frame comes back from an unstaged camera. |
| SuperK | Which Interbus module address the laser is on. |
| SPAD512 | That Pi Imaging's app is serving the port, and the four temperatures. |

## 6. Record what the data is of

Once, per sample or cooldown:

```python
lp.context(sample="NV-3", cooldown=7, operator="adrien")
```

Every file written afterwards carries that, plus the package version, the
git sha and whether the working tree was dirty, plus a per-point timestamp
array. None of it can be added retroactively — it describes the data at the
moment it was taken — which is why it is worth one line now.

## 7. First measurements, in this order

One new real device per step, so a failure has one cause.

1. **Connect and describe only** — step 5. Nothing moves.
2. **A CW scan** — the Nano-Drive plus the spectrometer, via the
   `generic_2d_scan` preset. Confirms the scan path, the live view, the
   automatic HDF5 file and the catalogue row on real hardware.
3. **ODMR** — add the Siglent and run `odmr_sweep`. It switches the source's
   output on and off around the sweep for you.
4. **Pulsed** — add the PicoHarp and run the Rabi preset of
   `pulsed_measurement`. Compare the recovered π-pulse against the mock's,
   which is known-good.
5. **Hardware-timed** — the NI PXI card via `ni_card` and
   `hardware_timed_scan`. **DAQmx before the R-Series**: the FPGA needs
   gateware compiled from a LabVIEW FPGA project that nobody can ship, so
   treat it as a separate project after DAQmx works.

Then the second setup, in the same way.

## Where things live

| | |
|---|---|
| `~/.labpilot/config/instruments/` | instrument sets, one `.cfg` per rig |
| `~/.labpilot/config/` | UI block configs, NI model overrides |
| `~/.labpilot/workflows/` | your own workflow scripts |
| `~/.labpilot/sequences/` | saved pulse sequences |
| `~/.labpilot/data/` | runs, as HDF5, plus the catalogue index |

Set `LABPILOT_HOME` to put all of that somewhere else — on a lab PC, a data
drive rather than a user profile.

## One thing deliberately not done

**There is no authentication.** The API has full instrument control and no
login. That is acceptable only because the backend binds to `127.0.0.1` —
this machine only — which is the default.

**If that ever changes**, if anyone passes `--host 0.0.0.0` so a second
machine can reach it, a shared token becomes a prerequisite rather than an
improvement. In a lab with a Class 4 laser on the same API, that is a safety
question and not a security one.
