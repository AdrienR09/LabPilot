#!/usr/bin/env python3
"""Print a connected NI card's real inventory as a `models.toml` block.

The model table in `instruments/NI/models.toml` was entered by hand from
NI's published specifications, which is the only way to know what a card
has when no card is present — and it is exactly as reliable as hand-entered
data ever is. This closes that loop: run it on a machine with the card in
it, and NI-DAQmx answers for itself.

    python scripts/ni_probe.py                 # every device NI-MAX knows
    python scripts/ni_probe.py Dev1            # just this one
    python scripts/ni_probe.py --check Dev1    # against the shipped table

Paste the printed block into `~/.labpilot/config/ni_models.toml`, which is
merged over the packaged table entry by entry. A correction worth having
everywhere is worth sending upstream as a patch to `models.toml` too.

Needs `nidaqmx` and the NI-DAQmx runtime — i.e. it only runs where the
card does, which is the point.
"""

from __future__ import annotations

import argparse
import sys

from labpilot.instruments.NI.models import find_model, normalise_number


def devices() -> list[str]:
    import nidaqmx

    return [device.name for device in nidaqmx.system.System().devices]


def probe(name: str) -> dict[str, object]:
    """What DAQmx says this device is.

    Each property is read on its own: a card that does not implement one
    should leave that field out of the block rather than abort the probe,
    since an absent field in the table means "not stated" and is
    harmless.
    """
    import nidaqmx

    device = nidaqmx.system.Device(name)
    found: dict[str, object] = {}

    def ask(key: str, get) -> None:
        try:
            value = get()
        except Exception:
            return
        if value not in (None, [], ()):
            found[key] = value

    ask("product", lambda: device.product_type)
    ask("number", lambda: normalise_number(device.product_type))
    ask("ai", lambda: len(device.ai_physical_chans.channel_names))
    ask("ao", lambda: len(device.ao_physical_chans.channel_names))
    ask("counters", lambda: len(device.co_physical_chans.channel_names))
    ask("dio", lambda: len(device.di_lines.channel_names))
    ask("pfi", lambda: len([t for t in device.terminals if "/pfi" in t.lower()]))
    ask("ai_rate", lambda: float(device.ai_max_single_chan_rate))
    ask("ao_rate", lambda: float(device.ao_max_rate))
    ask("ai_ranges", lambda: sorted({float(r) for r in device.ai_voltage_rngs if r > 0}))
    ask("timebase", lambda: float(device.ci_max_timebase))
    ask("serial", lambda: f"{device.dev_serial_num:08X}")
    return found


def as_toml(found: dict[str, object]) -> str:
    lines = ["[[card]]"]
    number = found.get("number", "unknown")
    lines.append(f'number = "{number}"')
    product = str(found.get("product", ""))
    bus = product.split("-")[0] if "-" in product else ""
    if bus:
        lines.append(f'buses = ["{bus}"]')
    for key in ("ai", "ao", "dio", "pfi", "counters"):
        if key in found:
            lines.append(f"{key} = {found[key]}")
    for key in ("ai_rate", "ao_rate", "timebase"):
        if key in found:
            lines.append(f"{key} = {found[key]!r}")
    if "ai_ranges" in found:
        lines.append(f"ai_ranges = {found['ai_ranges']}")
    lines.append(f'notes = "Probed from {product} serial {found.get("serial", "?")}."')
    return "\n".join(lines)


def check(found: dict[str, object]) -> int:
    """Compare a probed card with the shipped table, and say where they
    differ. Exit code 1 on any difference, so CI on a machine with a card
    can keep the table honest."""
    product = str(found.get("product", ""))
    try:
        model = find_model(product)
    except KeyError as exc:
        print(exc)
        print("\nAdd it:\n")
        print(as_toml(found))
        return 1

    differences = [
        (key, getattr(model, key), found[key])
        for key in ("ai", "ao", "counters", "pfi", "dio")
        if key in found and getattr(model, key) != found[key]
    ]
    if not differences:
        print(f"{product}: matches the table entry for {model.number}.")
        return 0

    print(f"{product}: the table entry for {model.number} disagrees with the card.")
    for key, table, device in differences:
        print(f"  {key}: table says {table}, card says {device}")
    print("\nThe card is right. Override it:\n")
    print(as_toml(found))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", nargs="*", help="NI-MAX device name(s), e.g. Dev1")
    parser.add_argument(
        "--check", action="store_true",
        help="compare with the shipped table instead of printing a block",
    )
    args = parser.parse_args()

    try:
        names = args.device or devices()
    except ImportError:
        print(
            "This needs the nidaqmx package and the NI-DAQmx runtime, which "
            "only exist where the card does (Windows or Linux; NI ships no "
            "macOS driver). Configuring a card needs neither — see "
            "instruments/NI/models.py.",
            file=sys.stderr,
        )
        return 2

    if not names:
        print("NI-DAQmx reports no devices.", file=sys.stderr)
        return 2

    status = 0
    for name in names:
        found = probe(name)
        if args.check:
            status |= check(found)
        else:
            print(f"# {name}: {found.get('product', 'unknown')}")
            print(as_toml(found))
            print()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
