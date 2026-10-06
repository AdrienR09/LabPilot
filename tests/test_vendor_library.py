"""Finding a vendor DLL before connecting, rather than failing at connect.

Three adapters need a library that arrives with the manufacturer's driver
installation and has no PyPI package: both Mad City Labs stages and the
PicoHarp 300. Each accepted a `library=` path already, and each searched the
usual places itself — but only at connect time, where the answer arrives as
an exception from inside ctypes. These tests cover answering it beforehand,
which is what the "Find" button beside the path field does.

The architecture check is the part worth having. A 32-bit library and a
64-bit Python is the commonest mistake with any of them, and it fails with
`WinError 193` — "not a valid Win32 application" — which reads like file
corruption. The word size is stated in the PE header, so it is read from the
file rather than discovered by loading it: no side effects, and it works on
a Mac looking at a DLL someone copied over.
"""

from __future__ import annotations

import struct

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from labpilot.core.api import dashboard as dashboard_module
from labpilot.instruments._vendor_library import (
    VendorLibrary,
    find_library,
    interpreter_word_size,
    pe_machine,
)
from labpilot.instruments.connections import CONNECTION_METHODS
from labpilot.instruments.MadCityLabs.micro_drive import MicroDriveAdapter
from labpilot.instruments.MadCityLabs.nano_drive import NanoDriveAdapter
from labpilot.instruments.PicoQuant.picoharp300 import PicoHarp300Adapter

MACHINE_X64 = 0x8664
MACHINE_I386 = 0x014C

ADAPTERS = [
    pytest.param(NanoDriveAdapter, "mcl_nano_drive", id="nano_drive"),
    pytest.param(MicroDriveAdapter, "mcl_micro_drive", id="micro_drive"),
    pytest.param(PicoHarp300Adapter, "picoharp_300", id="picoharp_300"),
]


def write_pe(path, machine: int, *, pe_offset: int = 0x80) -> None:
    """A file with a structurally real PE header and nothing else in it.

    Enough for `pe_machine`, which reads the DOS stub's `e_lfanew`, checks
    the PE signature and takes the two machine bytes — and deliberately not
    a loadable library, since nothing here loads one.
    """
    blob = bytearray(pe_offset + 8)
    blob[0:2] = b"MZ"
    blob[0x3C:0x40] = struct.pack("<I", pe_offset)
    blob[pe_offset:pe_offset + 4] = b"PE\0\0"
    blob[pe_offset + 4:pe_offset + 6] = struct.pack("<H", machine)
    path.write_bytes(bytes(blob))


# --- Reading the word size out of the file ---------------------------------


@pytest.mark.parametrize(
    ("machine", "expected"),
    [(MACHINE_X64, "64-bit"), (MACHINE_I386, "32-bit"), (0xAA64, "64-bit (ARM)")],
)
def test_the_word_size_is_read_from_the_pe_header(tmp_path, machine, expected):
    dll = tmp_path / "vendor.dll"
    write_pe(dll, machine)
    assert pe_machine(dll) == expected


@pytest.mark.parametrize(
    "content",
    [b"", b"MZ", b"not a library at all", b"\x7fELF" + b"\0" * 40],
    ids=["empty", "truncated", "text", "elf"],
)
def test_anything_that_is_not_a_pe_file_reports_no_word_size(tmp_path, content):
    """"Cannot tell" and "wrong" must stay distinguishable — refusing a
    library over an unreadable header would be worse than letting the load
    attempt speak for itself."""
    dll = tmp_path / "vendor.dll"
    dll.write_bytes(content)
    assert pe_machine(dll) == ""


def test_a_missing_file_reports_no_word_size(tmp_path):
    assert pe_machine(tmp_path / "absent.dll") == ""


# --- Searching -------------------------------------------------------------


def _spec(*candidates: str) -> VendorLibrary:
    return VendorLibrary(
        parameter="library",
        product="Test Stage",
        vendor="Test Vendor",
        candidates=candidates,
        installer="the vendor's driver installation",
    )


def test_a_library_at_a_known_path_is_found(tmp_path):
    dll = tmp_path / "vendor.dll"
    write_pe(dll, MACHINE_X64 if interpreter_word_size() == "64-bit" else MACHINE_I386)

    found = find_library(_spec(str(dll)))

    assert found.found
    assert found.path == str(dll)
    assert not found.mismatched
    assert str(dll) in found.message


def test_the_first_candidate_that_exists_wins(tmp_path):
    """The adapter tries them in order, so this has to report the same one
    a connect would load — not merely any that exists."""
    first = tmp_path / "first.dll"
    second = tmp_path / "second.dll"
    for path in (first, second):
        write_pe(path, MACHINE_X64)

    found = find_library(_spec(str(tmp_path / "absent.dll"), str(first), str(second)))

    assert found.path == str(first)


def test_a_library_of_the_wrong_word_size_is_found_but_refused(tmp_path):
    other = MACHINE_I386 if interpreter_word_size() == "64-bit" else MACHINE_X64
    dll = tmp_path / "vendor.dll"
    write_pe(dll, other)

    found = find_library(_spec(str(dll)))

    assert found.found
    assert found.mismatched
    assert found.architecture != found.interpreter
    assert "cannot be loaded" in found.message


def test_an_unreadable_header_is_not_treated_as_a_mismatch(tmp_path):
    dll = tmp_path / "vendor.dll"
    dll.write_bytes(b"something else entirely")

    found = find_library(_spec(str(dll)))

    assert found.found
    assert found.architecture == ""
    assert not found.mismatched


def test_nothing_found_says_where_it_looked_and_where_to_get_it(tmp_path):
    found = find_library(_spec(str(tmp_path / "absent.dll"), "nowhere.dll"))

    assert not found.found
    assert str(tmp_path / "absent.dll") in found.searched
    assert "pip-install" in found.message
    assert "driver installation" in found.message


def test_a_bare_name_is_looked_for_on_the_path(tmp_path, monkeypatch):
    dll = tmp_path / "onpath.dll"
    write_pe(dll, MACHINE_X64 if interpreter_word_size() == "64-bit" else MACHINE_I386)
    monkeypatch.setenv("PATH", str(tmp_path))

    found = find_library(_spec("onpath.dll"))

    assert found.found
    assert found.path == str(dll)


def test_a_windows_path_is_classified_as_a_path_on_every_platform():
    """`os.path.isabs` calls a Windows path relative on POSIX, which put
    every candidate in the search-the-PATH bucket — wrong everywhere, and
    invisible on the machine that matters."""
    spec = _spec(r"C:\Program Files\Vendor\lib.dll", "lib.dll", "/opt/vendor/lib.so")

    assert spec.paths == (r"C:\Program Files\Vendor\lib.dll", "/opt/vendor/lib.so")
    assert spec.names == ("lib.dll",)


# --- What the adapters declare ---------------------------------------------


@pytest.mark.parametrize(("adapter_cls", "adapter_key"), ADAPTERS)
def test_each_adapter_declares_the_parameter_its_constructor_takes(
    adapter_cls, adapter_key
):
    """A found path is written into this field, so the name has to be one
    the constructor actually accepts or the search is decorative."""
    import inspect

    spec = adapter_cls.vendor_library()
    accepted = set(inspect.signature(adapter_cls.__init__).parameters)
    assert spec.parameter in accepted


@pytest.mark.parametrize(("adapter_cls", "adapter_key"), ADAPTERS)
def test_each_adapter_declares_somewhere_to_look(adapter_cls, adapter_key):
    spec = adapter_cls.vendor_library()
    assert spec.candidates
    assert spec.product and spec.vendor and spec.installer


@pytest.mark.parametrize(("adapter_cls", "adapter_key"), ADAPTERS)
def test_the_declared_connection_method_offers_that_field(adapter_cls, adapter_key):
    """The catalogue has to route these to the form that has the control."""
    from labpilot.instruments.catalog import INSTRUMENT_CATALOG

    entry = next(m for m in INSTRUMENT_CATALOG if m.adapter_key == adapter_key)
    assert "vendor_library" in entry.connection_types

    fields = {f.name for f in CONNECTION_METHODS["vendor_library"].fields}
    assert adapter_cls.vendor_library().parameter in fields


def test_the_searched_candidates_are_the_ones_the_loader_tries():
    """Reporting a different list from the one a connect uses would be
    worse than reporting nothing."""
    from labpilot.instruments.MadCityLabs.nano_drive import _Madlib
    from labpilot.instruments.PicoQuant.picoharp300 import LIBRARY_NAMES

    assert NanoDriveAdapter.vendor_library().candidates == _Madlib.candidates
    assert PicoHarp300Adapter.vendor_library().candidates == LIBRARY_NAMES


# --- Over REST -------------------------------------------------------------


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(dashboard_module.router)
    return TestClient(app)


@pytest.mark.parametrize(("adapter_cls", "adapter_key"), ADAPTERS)
def test_the_route_reports_the_search(client, adapter_cls, adapter_key):
    response = client.get(f"/api/dashboard/catalog/{adapter_key}/vendor-library")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["parameter"] == adapter_cls.vendor_library().parameter
    assert data["product"] == adapter_cls.vendor_library().product
    assert isinstance(data["found"], bool)
    assert data["message"]
    assert data["interpreter"] in ("32-bit", "64-bit")


def test_an_adapter_needing_no_library_is_a_404_not_an_error(client):
    response = client.get("/api/dashboard/catalog/mock_basic_detector_0d/vendor-library")

    assert response.status_code == 404
    assert "does not need a vendor library" in response.json()["detail"]


def test_an_unknown_adapter_is_a_404(client):
    response = client.get("/api/dashboard/catalog/not_an_adapter/vendor-library")

    assert response.status_code == 404
    assert "No adapter registered" in response.json()["detail"]


def test_the_route_loads_nothing(client, monkeypatch):
    """It must stay safe to press with hardware powered on: a find that
    loaded the library would run whatever the vendor put in its entry
    point, and a find that connected could move a stage."""
    import ctypes

    def forbidden(*args, **kwargs):
        raise AssertionError("the search loaded a library")

    monkeypatch.setattr(ctypes, "CDLL", forbidden)
    monkeypatch.setattr(ctypes, "WinDLL", forbidden, raising=False)

    assert client.get("/api/dashboard/catalog/mcl_nano_drive/vendor-library").status_code == 200
