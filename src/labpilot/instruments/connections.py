"""Connection-method registry — the field shape for each way an
instrument can be reached (VISA, serial/COM, TCP/IP, USB serial number, or
none for mocks/fixtures), selectable when an instrument is loaded rather
than assumed from its backend.

Mirrors `adapter_registry`'s pattern: a small, greppable table, not a
class hierarchy — `InstrumentMetadata.connection_types` (catalog.py)
names which of these keys apply to a given catalog entry; the frontend's
"Connect Device" flow renders the chosen method's `fields` as the
connection-parameter form.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ConnectionField", "ConnectionMethod", "CONNECTION_METHODS", "get_connection_method"]


@dataclass(frozen=True)
class ConnectionField:
    name: str  # key placed into connection_params, e.g. "port"
    dtype: str  # "str" | "int" | "float"
    label: str  # human-readable form label
    default: object = None


@dataclass(frozen=True)
class ConnectionMethod:
    key: str
    label: str
    fields: tuple[ConnectionField, ...]


CONNECTION_METHODS: dict[str, ConnectionMethod] = {
    "visa": ConnectionMethod(
        "visa", "VISA",
        (ConnectionField("resource", "str", "VISA resource string", "GPIB::1"),),
    ),
    "serial": ConnectionMethod(
        "serial", "Serial / COM port",
        (
            ConnectionField("port", "str", "Serial port", "COM3"),
            ConnectionField("baudrate", "int", "Baud rate", 9600),
            ConnectionField("timeout", "float", "Timeout (s)", 1.0),
        ),
    ),
    "tcp": ConnectionMethod(
        "tcp", "TCP/IP",
        (
            ConnectionField("host", "str", "Host", "192.168.1.100"),
            ConnectionField("port", "int", "Port", 5025),
        ),
    ),
    "usb_serial_number": ConnectionMethod(
        "usb_serial_number", "USB (serial number)",
        (ConnectionField("serial_number", "str", "Device serial number", ""),),
    ),
    # An NI card is not reached by an address: DAQmx already knows it by
    # the name NI-MAX gave it. What has to be said instead is which card
    # it is and what is plugged into which terminal — see
    # instruments/NI/channels.py for the one-line channel syntax, which
    # exists so the whole wiring fits in a form field like this one.
    "ni_daqmx": ConnectionMethod(
        "ni_daqmx", "NI-DAQmx device",
        (
            ConnectionField("device", "str", "NI-MAX device name", "Dev1"),
            ConnectionField("model", "str", "Card model", "PCIe-6363"),
            ConnectionField(
                "channels", "str", "Channels (name=terminal, comma separated)",
                "x=ao0, y=ao1, apd=ctr0/pfi8",
            ),
        ),
    ),
    # An R-Series card is an FPGA: what it *does* is whatever gateware was
    # compiled onto it, so the bitfile is the real setting. Leaving it
    # blank is a first-class choice, not an omission — the pulsed
    # measurement then picks the image its sequence needs from the library
    # in ~/.labpilot/config/ni_rseries.toml. See instruments/NI/bitfiles.py.
    "ni_fpga": ConnectionMethod(
        "ni_fpga", "NI R-Series (FPGA)",
        (
            ConnectionField("resource", "str", "RIO resource name", "RIO0"),
            ConnectionField("model", "str", "Card model", "generic"),
            ConnectionField(
                "bitfile", "str",
                "Bitfile (.lvbitx; blank = chosen from the library)", "",
            ),
        ),
    ),
    # seabreeze finds Ocean Optics spectrometers over USB itself, so the
    # only address is which one — and naming the model makes its exposure
    # limits and pixel count known before it is plugged in.
    "ocean_optics": ConnectionMethod(
        "ocean_optics", "Ocean Optics (USB)",
        (
            ConnectionField(
                "serial_number", "str", "Serial number (blank = first found)", ""
            ),
            ConnectionField("model", "str", "Model (blank = ask the device)", ""),
        ),
    ),
    # A Pulse Streamer is reached over the network, but by an address its
    # own constructor calls `resource` rather than a host/port pair — so it
    # is not the `tcp` method, whose fields the adapter would discard.
    "hostname": ConnectionMethod(
        "hostname", "Hostname / IP address",
        (ConnectionField("resource", "str", "Hostname or IP address", "192.168.1.100"),),
    ),
    # A PulseBlaster is a PCI card with no address at all: spinapi selects it
    # by index. The clock rate and channel count are the settings that decide
    # what a sequence compiles to, so they belong in the same form.
    "spincore": ConnectionMethod(
        "spincore", "SpinCore board",
        (
            ConnectionField("board", "int", "Board index", 0),
            ConnectionField("clock_mhz", "float", "Clock (MHz)", 500.0),
            ConnectionField("channels", "int", "Digital channels", 24),
        ),
    ),
    # A library that ships with the manufacturer's driver installation and
    # has no PyPI package: both Mad City Labs stages and the PicoHarp. The
    # field is optional on purpose — blank means "search the usual places",
    # which is what works on a standard installation. `_vendor_library.py`
    # is what fills it in when that is not enough, and the adapter class
    # declares its own candidates via `vendor_library()`.
    "vendor_library": ConnectionMethod(
        "vendor_library", "Vendor library (DLL)",
        (
            ConnectionField(
                "library", "str",
                "Library path — blank to search the default locations", "",
            ),
        ),
    ),
    "none": ConnectionMethod("none", "No connection (mock/simulated)", ()),
}


def get_connection_method(key: str) -> ConnectionMethod:
    return CONNECTION_METHODS[key]
