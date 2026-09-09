"""The gated-counter contract — a device that counts photons per readout.

The other half of a pulsed rig. The pulser plays the sequence and raises a
gate once per readout; this counts events into time bins inside each gate,
and hands back a 2-D `(gate, time_bin)` trace.

## configure_gates returns what it actually set

Not a convention borrowed for tidiness — it is the whole reason the
constraint layer exists. A counter's bin width comes from a discrete list
its clock can divide down to, so a request of 1.4 ns is not illegal, it is
simply going to become 1 ns. Qudi's `FastCounterInterface.configure()`
returns the binwidth, record length and gate count it really applied, with
the interface documented as "the caller MUST use the return value", and
that is right: a silently ignored request is how someone spends an
afternoon wondering why their T2 is 40% short.

## get_trace returns a Dataset

A gated counter's natural output is exactly what `Dataset` was built for:

    DataArray(
        values=(gate, bin),
        axes=(Axis("readout", kind="index"),
              Axis("time", kind="time", unit="s")),
    )

Qudi returns a bare `(ndarray, info_dict)` and every consumer re-derives
what the axes mean. Here the axes travel with the numbers, so the run
lands in HDF5 with real coordinates and a view can lay itself out without
being told.

## Gates, not laser pulses

The gate count comes from the sequence's own `readouts()`, which counts
rising edges of the gate channel. T1 polarises with the laser and only
then reads out, so counting laser edges would score the initialisation as
a second readout and silently halve the sweep. The sequence and the
counter agree because they count the same thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from labpilot.core.device.capabilities import GATED_COUNTER
from labpilot.core.device.constraints import Constraints, Quantised

if TYPE_CHECKING:
    from labpilot.core.data.dataset import Dataset

__all__ = [
    "BIN_WIDTH",
    "GATES",
    "RECORD_LENGTH",
    "GateConfig",
    "GatedCounterMixin",
]

#: The constraint names a counter's `counter_constraints()` should use, so
#: a caller can quantise a request before making it.
BIN_WIDTH = "bin_width_s"
RECORD_LENGTH = "record_length_s"
"""How long a window is recorded after each gate opens. Longer than the
laser pulse, deliberately: the decaying tail is what the reference window
of a normalised readout is taken from."""
GATES = "gates"


@dataclass(frozen=True, slots=True)
class GateConfig:
    """What the counter is really set to, after quantisation.

    Returned by `configure_gates` and used by the caller in place of what
    it asked for. `bins` is derived rather than stored so it cannot
    disagree with the two values it comes from.
    """

    bin_width_s: float
    record_length_s: float
    gates: int
    quantised: Quantised = field(default_factory=lambda: Quantised({}))

    @property
    def bins(self) -> int:
        """Time bins per gate — the second dimension of the trace."""
        if self.bin_width_s <= 0:
            return 0
        return max(round(self.record_length_s / self.bin_width_s), 1)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.gates, self.bins)

    @property
    def exact(self) -> bool:
        return self.quantised.exact

    def report(self) -> str:
        return self.quantised.report()

    def to_dict(self) -> dict[str, Any]:
        return {
            "bin_width_s": self.bin_width_s,
            "record_length_s": self.record_length_s,
            "gates": self.gates,
            "bins": self.bins,
            "exact": self.exact,
            "adjustments": [str(a) for a in self.quantised.adjustments],
        }


class GatedCounterMixin:
    """A device that counts events into time bins, one window per gate.

    Opt in by inheritance, the same convention `HardwareScanMixin` and
    `PulserMixin` use:

        class MyCounter(GatedCounterMixin, AdapterBase): ...
    """

    CAPABILITY = GATED_COUNTER

    def counter_constraints(self) -> Constraints:
        """What bin widths, record lengths and gate counts this device
        supports. Synchronous and answerable without hardware, like
        `PulserMixin.pulser_constraints`."""
        raise NotImplementedError

    async def configure_gates(
        self, bin_width_s: float, record_length_s: float, gates: int
    ) -> GateConfig:
        """Arm for `gates` windows and report what was **actually** set.

        The caller must use the returned values rather than its own
        request — see the module docstring. Does not start counting.
        """
        raise NotImplementedError

    async def start_counting(self) -> None:
        """Begin accepting gates. Returns immediately; poll `get_trace()`."""
        raise NotImplementedError

    async def stop_counting(self) -> None:
        """Stop, keeping whatever has been accumulated.

        Must be safe to call when nothing is running: it is what an
        aborted run calls, and an abort cannot know how far the run got.
        """
        raise NotImplementedError

    async def get_trace(self) -> Dataset:
        """Everything counted so far, as a 2-D `(gate, time_bin)` array
        with real axes. Safe to call repeatedly, running or not."""
        raise NotImplementedError

    async def counter_status(self) -> dict[str, Any]:
        """`{"running": bool, "sweeps": int}` — how many complete passes
        over every gate have been accumulated, which is what a pulsed run
        counts its progress in."""
        raise NotImplementedError
