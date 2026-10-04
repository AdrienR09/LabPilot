# Getting at the data

Every run is written to HDF5 and indexed as it finishes — nobody clicks
Save. This page is the other half: opening one again.

```python
lp.runs[0]                      # the newest run's catalogue row
ds = lp.open(lp.runs[0]["run_uid"])
ds.primary().values.shape       # (6, 5)
ds.axes()                       # (Axis('x', mm), Axis('y', mm))
dict(ds.meta.context)           # {'sample': 'NV-3', 'cooldown': 7}
```

`lp.open` takes a run id or a path, because a file a colleague sent you is
the same job and ends in the same object.

## What is in the file

A `Dataset` is self-describing, and so is the file. Each array carries its
unit; each axis is a real HDF5 **dimension scale** attached to the
dimension it indexes, which is the standard convention — so h5py, xarray
and MATLAB all read the coordinates without being told anything.

Alongside the numbers:

| | |
|---|---|
| `meta.run_uid`, `meta.plan_name`, `meta.timestamp` | which run this was |
| `meta.params` | the plan's parameters — the sweep bounds, the averaging count |
| `meta.software` | package version, git sha, and whether the tree was dirty |
| `meta.context` | whatever `lp.context(...)` was set to: sample, cooldown, operator |
| `meta.devices` | every participating instrument's full `DeviceSchema` |
| a `point_time` array | when each point was taken, as its own coordinate |

None of the last four can be added later — they describe the data at the
moment it was taken. That is why `lp.context(sample=...)` is worth the one
line before a session.

## xarray

```python
x = ds.to_xarray()
x.data.sel(x=0.5, y=0.0, method="nearest")   # by value, not by index
x.data.mean(dim="y")                          # a labelled reduction
x.attrs["context/sample"]                     # 'NV-3'
```

Needs `pip install "labpilot[analysis]"`.

**There is deliberately no analysis layer here.** xarray, scipy and
`core/analysis/fits.py` are the analysis layer; the useful thing to build
was the bridge, and it is one method because the axes were already real.
`core/analysis/fits.py` has `fit_dip`, `fit_rabi` and `fit_decay` if you
want the same fits the result views draw.

## Reading a file with no LabPilot at all

The point of using the standard convention. In a notebook on another
machine:

```python
import h5py

with h5py.File("20261004-190132_scan_220e42d3.h5") as f:
    run = f["run"]
    dict(f.attrs)                     # {'created_with': 'LabPilot', ...}
    dict(run.attrs)                   # run_uid, software/*, context/*
    dict(run["params"].attrs)         # the plan's parameters
    counts = run["data"][()]          # the numbers
    x = run["axes/x"][()]             # its first coordinate
    [d.label for d in run["data"].dims]   # ['x', 'y'] — which is which
```

Nothing above imports LabPilot, and the dimension labels are what say
which coordinate belongs to which axis of the array.

`xr.open_dataset(path, group="run")` is **not** a route to rely on:
xarray's HDF5 backends go through netCDF conventions, which are stricter
than plain dimension scales, and without `h5netcdf` or `netcdf4`
installed it refuses the file outright. `Dataset.from_hdf5(path).to_xarray()`
is the supported path and does the same job in one line.

## Two file layouts, one reader

`Dataset.to_hdf5("scan.h5")` writes the dataset at the file root. An
automatically saved run nests it under a `run` group, with
`created_with` and `format_version` at the root. `Dataset.from_hdf5`
accepts either — it resolves which group holds the data rather than making
you know — and both carry the same content, including the parameters and
the device schemas.

That last part was not always true: the parameters and schemas used to be
written by the automatic path *after* `to_hdf5` had written everything
else, so a file you exported by hand from the console was missing exactly
the metadata that makes a file worth sending. One writer now.
