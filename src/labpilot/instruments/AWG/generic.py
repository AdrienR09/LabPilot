"""Function/arbitrary-waveform generator adapters for pylablib.

Every class in `pylablib.devices.AWG` subclasses `GenericAWG` and shares
its frequency/amplitude/offset/output-enable API (verified against the
installed package) — one generic wrapper (`PylablibAWGAdapter`, in
`instruments/_generic_pylablib.py`) covers every vendor here, the same
pattern already used for pylablib stages/cameras.

Attribution: Wraps pylablib by Alexey Shkarin — GPL v3 licence
"""

from __future__ import annotations

try:
    from pylablib.devices import AWG
except ImportError:
    AWG = None

if AWG is not None:
    from labpilot.instruments._base import adapter_registry
    from labpilot.instruments._generic_pylablib import PylablibAWGAdapter

    class Agilent33220AAdapter(PylablibAWGAdapter):
        def __init__(self, addr: str, name: str | None = None, **kwargs) -> None:
            super().__init__(device_class=AWG.Agilent33220A, name=name or "agilent_33220a", addr=addr, **kwargs)

    class Agilent33500Adapter(PylablibAWGAdapter):
        def __init__(self, addr: str, name: str | None = None, **kwargs) -> None:
            super().__init__(device_class=AWG.Agilent33500, name=name or "agilent_33500", addr=addr, **kwargs)

    class RigolDG1000Adapter(PylablibAWGAdapter):
        def __init__(self, addr: str, name: str | None = None, **kwargs) -> None:
            super().__init__(device_class=AWG.RigolDG1000, name=name or "rigol_dg1000", addr=addr, **kwargs)

    class TektronixAFG1000Adapter(PylablibAWGAdapter):
        def __init__(self, addr: str, name: str | None = None, **kwargs) -> None:
            super().__init__(device_class=AWG.TektronixAFG1000, name=name or "tektronix_afg1000", addr=addr, **kwargs)

    class InstekAFG2000Adapter(PylablibAWGAdapter):
        def __init__(self, addr: str, name: str | None = None, **kwargs) -> None:
            super().__init__(device_class=AWG.InstekAFG2000, name=name or "instek_afg2000", addr=addr, **kwargs)

    adapter_registry.register("pylablib_agilent33220a", Agilent33220AAdapter)
    adapter_registry.register("pylablib_agilent33500", Agilent33500Adapter)
    adapter_registry.register("pylablib_rigol_dg1000", RigolDG1000Adapter)
    adapter_registry.register("pylablib_tektronix_afg1000", TektronixAFG1000Adapter)
    adapter_registry.register("pylablib_instek_afg2000", InstekAFG2000Adapter)
