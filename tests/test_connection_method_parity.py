"""The frontend's connection-method table must match the backend's.

`instruments/connections.py` holds the field shape for each way an
instrument can be reached, and `DeviceModal/index.tsx` carries a hand-written
mirror of it — a deliberate choice, recorded in its own comment: stable UI
metadata rather than a route serving live state.

What the comment did not come with is anything keeping the two in step, and
they had already drifted. `ni_daqmx`, `ni_fpga` and `ocean_optics` existed in
the backend and were missing from the mirror, so choosing an NI card, an
R-Series FPGA or an Ocean Optics spectrometer in the Devices modal rendered
no fields at all — `CONNECTION_METHODS[method]?.fields || []` falls back to
empty, silently, and the instrument was created with none of its wiring.
Three of the eight instruments on a confocal rig.

The frontend's field names are what actually reach the API, so they are the
half that matters: `create_adapter` filters `connection_params` against the
constructor signature, which means a name only the backend table knows is
never sent, and a name only the mirror knows is dropped on the floor.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from labpilot.core.frontend import frontend_source_dir
from labpilot.instruments.connections import CONNECTION_METHODS

MODAL = Path("src/components/DeviceModal/index.tsx")

# The object literal, from `const CONNECTION_METHODS` to its closing brace at
# column 0. Parsed rather than imported because it is TypeScript; a failure
# here means the declaration moved, which is itself worth being told about.
_TABLE = re.compile(
    r"const CONNECTION_METHODS:[^=]*=\s*\{(?P<body>.*?)^\};", re.DOTALL | re.MULTILINE
)
_METHOD = re.compile(r"^  (?P<key>[a-z_]+):\s*\{", re.MULTILINE)
_FIELD_NAME = re.compile(r"\bname:\s*'(?P<name>[^']+)'")


@pytest.fixture(scope="module")
def mirror() -> dict[str, list[str]]:
    """{method key: [field names]} as the frontend declares them."""
    source = frontend_source_dir()
    if source is None:
        pytest.skip("no front-end sources in this install")
    text = (source / MODAL).read_text()

    table = _TABLE.search(text)
    assert table, f"could not find the CONNECTION_METHODS literal in {MODAL}"
    body = table.group("body")

    # Each method owns the text from its own key up to the next one.
    starts = [(m.group("key"), m.start()) for m in _METHOD.finditer(body)]
    assert starts, f"found no connection methods in {MODAL}"
    bounds = [*(s for _, s in starts[1:]), len(body)]

    return {
        key: _FIELD_NAME.findall(body[start:end])
        for (key, start), end in zip(starts, bounds, strict=True)
    }


def test_the_same_methods_exist_on_both_sides(mirror):
    assert set(mirror) == set(CONNECTION_METHODS), (
        "connection methods have drifted — a method the UI does not know "
        "renders an empty form, and one the backend does not know is a "
        f"dropdown entry that configures nothing.\n"
        f"  backend only: {sorted(set(CONNECTION_METHODS) - set(mirror))}\n"
        f"  frontend only: {sorted(set(mirror) - set(CONNECTION_METHODS))}"
    )


@pytest.mark.parametrize("key", sorted(CONNECTION_METHODS))
def test_each_method_offers_the_same_fields_in_the_same_order(mirror, key):
    """Order as well as membership: the form is rendered in declaration
    order, and the backend table is what the docs describe."""
    if key not in mirror:
        pytest.skip(f"{key} is missing from the mirror — see the test above")
    expected = [f.name for f in CONNECTION_METHODS[key].fields]
    assert mirror[key] == expected


def test_every_catalogued_connection_type_is_a_real_method():
    """A catalogue entry naming a method that does not exist renders an
    empty form and a raw key as its label."""
    from labpilot.instruments.catalog import INSTRUMENT_CATALOG

    unknown: dict[str, list[str]] = {}
    for entry in INSTRUMENT_CATALOG:
        for method in entry.connection_types:
            if method not in CONNECTION_METHODS:
                unknown.setdefault(method, []).append(entry.adapter_key)

    assert not unknown, (
        "catalogue entries name connection methods that do not exist: "
        f"{json.dumps({k: v[:5] for k, v in unknown.items()}, indent=2)}"
    )
