"""What a device can do beyond read and write, composed rather than chained.

`DeviceSchema.kind` answers "what sort of thing is this?" with one of five
strings, which is right for a stage and wrong for a device whose
interesting behaviour is a contract of its own. A hardware-timed scanner
and a pulse sequencer are both `kind="generic"` — a label saying only that
neither fits the other four.

The previous answer was a single `isinstance` in `kinds._build`. It works,
and it is why `HardwareScanMixin` is the one typed-device mechanism here
that earned its keep. What it cannot do is compose: a second contract
means a second `isinstance` and an ordering question between them, a
device satisfying both is inexpressible, and the fact never leaves the
process — so `ui_blocks.toml`, which selects on `(kind, dimensionality)`,
puts every generic device in one bucket.

A capability is a string a mixin declares, composed off the MRO onto the
schema. These tests pin the three things that buys: composition, offline
visibility, and config selection.
"""

from __future__ import annotations

import pytest

from labpilot.core.device.capabilities import (
    GATED_COUNTER,
    HARDWARE_SCAN,
    PULSER,
    capabilities_of,
    with_capabilities,
)
from labpilot.core.device.kinds import (
    Detector,
    GenericInstrument,
    Motor,
    Scanner,
    wrap,
)
from labpilot.core.device.schema import DeviceSchema
from labpilot.instruments import adapter_registry
from labpilot.instruments._base import AdapterBase
from labpilot.instruments.hardware_scan_mixin import HardwareScanMixin


class _PulserMixin:
    """Stands in for the real one until the pulse subsystem lands."""

    CAPABILITY = PULSER


def _adapter(kind: str, *mixins, **schema_kwargs):
    schema = DeviceSchema(
        name="bench", kind=kind, readable={"value": "float64"}, **schema_kwargs
    )

    class _Adapter(*mixins, AdapterBase):
        @property
        def schema(self):
            return schema

        def _read_sync(self):
            return {"value": 1.0}

        def _connect_sync(self):
            pass

        def _disconnect_sync(self):
            pass

    return _Adapter()


# --- Composing ------------------------------------------------------------


def test_a_mixin_declares_its_capability():
    assert capabilities_of(_adapter("generic", HardwareScanMixin)) == {HARDWARE_SCAN}


def test_a_device_with_no_mixin_has_no_capabilities():
    assert capabilities_of(_adapter("detector")) == frozenset()


def test_two_mixins_both_report():
    """The case the isinstance chain could not express: it returned the
    first match and dropped the rest."""
    device = _adapter("generic", HardwareScanMixin, _PulserMixin)
    assert capabilities_of(device) == {HARDWARE_SCAN, PULSER}


def test_a_schema_may_declare_a_capability_without_the_mixin():
    """For a device that satisfies a contract by other means."""
    device = _adapter("detector", capabilities=frozenset({GATED_COUNTER}))
    assert GATED_COUNTER in capabilities_of(device)


def test_a_class_reports_its_capabilities_without_being_instantiated():
    """This is what puts a contract in the catalogue listing rather than
    only on a connected instrument."""
    assert HARDWARE_SCAN in capabilities_of(adapter_registry.get("mock_ni_scanner"))


def test_an_instance_attribute_cannot_forge_a_capability():
    device = _adapter("detector")
    device.CAPABILITY = PULSER
    assert capabilities_of(device) == frozenset()


# --- Choosing a wrapper ---------------------------------------------------


def test_the_existing_scanner_still_wraps_as_a_scanner():
    """The behaviour the isinstance line had, unchanged."""
    device = _adapter("generic", HardwareScanMixin)
    assert type(wrap(device)) is Scanner


def test_a_plain_generic_device_is_still_generic():
    assert type(wrap(_adapter("generic"))) is GenericInstrument


def test_a_kind_keeps_its_own_wrapper_when_it_has_no_capabilities():
    assert type(wrap(_adapter("motor"))) is Motor
    assert type(wrap(_adapter("counter"))) is Detector


def test_a_detector_that_also_scans_gets_both_apis():
    """A real instrument the previous mapping could not describe: `kind`
    decided everything, so the scan contract was invisible."""
    device = _adapter("detector", HardwareScanMixin)
    wrapper = wrap(device)

    assert isinstance(wrapper, Detector)
    assert isinstance(wrapper, Scanner)
    assert hasattr(wrapper, "read_value")      # from Detector
    assert hasattr(wrapper, "configure_scan")  # from Scanner


def test_a_composed_wrapper_is_still_the_same_object_every_time():
    """`session.get()` must keep handing back one instrument, not a new
    wrapper per lookup."""
    device = _adapter("detector", HardwareScanMixin)
    assert wrap(device) is wrap(device)


def test_two_devices_of_the_same_shape_share_one_composed_class():
    """Otherwise a rack of identical pulsers mints a class each."""
    first = _adapter("detector", HardwareScanMixin)
    second = _adapter("detector", HardwareScanMixin)
    assert type(wrap(first)) is type(wrap(second))


# --- Reaching the wire ----------------------------------------------------


def test_capabilities_are_joined_onto_the_schema():
    device = _adapter("generic", HardwareScanMixin)
    assert with_capabilities(device.schema, device).capabilities == {HARDWARE_SCAN}


def test_a_schema_with_nothing_to_add_is_returned_unchanged():
    device = _adapter("detector")
    assert with_capabilities(device.schema, device) is device.schema


def test_capabilities_survive_serialisation():
    """`ui_blocks.toml` and the REST clients select on this."""
    device = _adapter("generic", HardwareScanMixin)
    dumped = with_capabilities(device.schema, device).model_dump(mode="json")
    assert HARDWARE_SCAN in dumped["capabilities"]
    assert DeviceSchema(**dumped).capabilities == {HARDWARE_SCAN}


def test_describe_reports_capabilities_offline():
    described = adapter_registry.get("mock_ni_scanner").describe()
    assert described is not None
    assert HARDWARE_SCAN in described.capabilities


# --- Selecting UI blocks --------------------------------------------------

CONFIG = {
    "detector": {"0D": {"blocks": [{"type": "viewer"}]},
                 "GENERIC": {"blocks": [{"type": "actions"}]}},
    "capability": {PULSER: {"blocks": [{"type": "pulse_sequence_editor"}]}},
}


def _resolve(kind, dimensionality, capabilities=()):
    import sys
    from pathlib import Path

    desktop = Path(__file__).resolve().parents[1] / "src" / "labpilot" / "ui" / "desktop"
    if str(desktop) not in sys.path:
        sys.path.insert(0, str(desktop))
    from instrument_blocks import resolve_blocks

    return resolve_blocks(kind, dimensionality, CONFIG, capabilities)


def test_a_capability_section_wins_over_the_kind_bucket():
    """`config_kind` collapses generic to detector, so without this a pulse
    sequencer and a hardware-timed scanner get the same window."""
    assert _resolve("generic", "GENERIC", [PULSER]) == [
        {"type": "pulse_sequence_editor"}
    ]


def test_a_device_with_no_matching_capability_falls_through_to_its_kind():
    assert _resolve("generic", "GENERIC", [HARDWARE_SCAN]) == [{"type": "actions"}]


def test_selection_is_unchanged_when_nothing_declares_a_capability():
    assert _resolve("detector", "0D") == [{"type": "viewer"}]


@pytest.mark.parametrize("capabilities", [(), (HARDWARE_SCAN,)])
def test_an_unknown_combination_still_falls_back_rather_than_crashing(capabilities):
    assert _resolve("detector", "7D", capabilities) == [{"type": "viewer"}]
