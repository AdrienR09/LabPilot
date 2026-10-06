"""Command-line interface for LabPilot Core.

Provides CLI entry points for launching LabPilot applications and managing the system.
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    """Main CLI entry point for LabPilot."""
    parser = argparse.ArgumentParser(
        prog="labpilot",
        description="LabPilot Core - AI-native laboratory experiment operating system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  labpilot app                       Start the whole app: backend, front end, window
  labpilot app --no-window           Same, but for a browser instead of the Qt window
  labpilot app --dev                 Serve the front end from Vite, with hot reload
  labpilot start                     Start the backend only, on default port 8000
  labpilot start --port 8765         Start server on port 8765
  labpilot start --load session.json Load specific session configuration
  labpilot probe mock_basic_detector_0d  Connect one instrument and check its schema
  labpilot probe --all               Probe every instrument in your saved rig
  labpilot probe ocean_optics --offline  Print its declared schema, connecting nothing
  labpilot rig-templates             Ready-made instrument sets for a whole rig
  labpilot rig-init nv_confocal      Install one as your instrument set
  labpilot list-adapters             List all available instrument adapters
  labpilot list-adapters --tags camera   Filter adapters by tags
  labpilot --version                 Show version information
        """,
    )

    # Create subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # The whole application — replaces the launch.sh shell script
    app_parser = subparsers.add_parser(
        "app",
        help="Start the backend, the front end and the manager window together",
        description=(
            "Starts everything and shuts it all down together. The front end needs "
            "no setting up: an installed wheel carries the built bundle, and from a "
            "checkout this installs the npm dependencies and builds it if they are "
            "missing."
        ),
    )
    app_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind the backend to (default: 127.0.0.1, i.e. this machine only)",
    )
    app_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Backend port; another is chosen automatically if this one cannot be bound "
             "(default: 8000)",
    )
    app_parser.add_argument(
        "--frontend-port",
        type=int,
        default=3000,
        help="Dev-server port, only used when the front end runs under Vite (default: 3000)",
    )
    app_parser.add_argument(
        "--dev",
        action="store_true",
        help="Serve the front end from the Vite dev server (hot reload) even if a "
             "built bundle exists. Needs a checkout; installs its dependencies if "
             "they are missing.",
    )
    app_parser.add_argument(
        "--build",
        action="store_true",
        help="Rebuild the front end bundle before serving it, even if one already "
             "exists (a launch otherwise reuses it)",
    )
    app_parser.add_argument(
        "--no-window",
        action="store_true",
        help="Don't open the Qt manager window — print a URL to open in a browser instead",
    )
    app_parser.add_argument(
        "--safe-graphics",
        action="store_true",
        help="Render the manager window without the GPU. For a machine whose graphics "
             "driver QtWebEngine cannot use, or a remote-desktop session, where the "
             "window is otherwise blank or black.",
    )

    # Start server command
    start_parser = subparsers.add_parser("start", help="Start LabPilot server")
    start_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run server on (default: 8000)",
    )
    start_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind the backend to (default: 127.0.0.1, i.e. this "
             "machine only). Binding a wider address exposes full, "
             "unauthenticated instrument control to the network — see the "
             "warning `labpilot start` prints if you do.",
    )
    start_parser.add_argument(
        "--load",
        type=str,
        help="Path to session configuration file to load",
    )
    start_parser.add_argument(
        "--config-dir",
        type=str,
        help="Path to configuration directory",
    )
    start_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    start_parser.add_argument(
        "--log-level",
        type=str,
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Logging level (default: info)",
    )

    # Probe one instrument — the first thing to run on new hardware
    probe_parser = subparsers.add_parser(
        "probe",
        help="Connect one instrument, read it once, and check its declared schema",
        description=(
            "Connects the named adapter, prints the schema it declares, prints it "
            "again once the device has answered, reads once, and reports every "
            "place the hardware disagrees with the declaration. It writes nothing "
            "and moves nothing: only connect, schema, read, disconnect. Exits 0 on "
            "agreement, 1 on a disagreement, 2 if it could not get far enough to "
            "tell."
        ),
    )
    probe_parser.add_argument(
        "adapter_key",
        nargs="?",
        help="Adapter to probe, as `labpilot list-adapters` prints it. Omit it "
             "with --all to probe a whole saved rig instead.",
    )
    probe_parser.add_argument(
        "--all",
        action="store_true",
        help="Probe every instrument in the active instrument set, using the "
             "connection parameters it already holds. This is what bring-up "
             "looks like: one command, a table at the end.",
    )
    probe_parser.add_argument(
        "--config",
        default="",
        metavar="NAME",
        help="Probe this saved instrument set instead of the active one "
             "(implies --all)",
    )
    probe_parser.add_argument(
        "--resource",
        help="The instrument's address — a VISA string, a serial port, a device name. "
             "Shorthand for --param resource=...",
    )
    probe_parser.add_argument(
        "--param",
        action="append",
        metavar="NAME=VALUE",
        help="Any other constructor argument, repeatable (--param serial=12345). "
             "Numbers and true/false/none are converted; anything else stays text.",
    )
    probe_parser.add_argument(
        "--offline",
        action="store_true",
        help="Print the declared schema and stop — connect to nothing. Useful before "
             "the instrument is wired, and to review what an adapter claims.",
    )
    probe_parser.add_argument(
        "--no-read",
        action="store_true",
        help="Connect and compare schemas, but take no reading. For an instrument "
             "where even a read costs something (a long camera exposure).",
    )
    probe_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the whole probe as JSON instead of a report, for a script or a "
             "bug report",
    )

    # Ready-made instrument sets, so a lab PC is not set up by hand
    subparsers.add_parser(
        "rig-templates",
        help="List the ready-made instrument sets shipped with LabPilot",
        description=(
            "Setting up a lab PC otherwise means the Devices dialog once per "
            "instrument: pick the adapter out of several hundred, name it, "
            "choose a connection method, type an address. A template is a "
            "saved instrument set shipped with the package, so installing one "
            "writes the same config that dialog would have produced."
        ),
    )

    rig_init_parser = subparsers.add_parser(
        "rig-init",
        help="Install a ready-made instrument set and make it active",
        description=(
            "Writes a template out as ~/.labpilot/config/instruments/<name>.cfg "
            "and activates it. From then on it is an ordinary config: editable "
            "in the Devices tab and switchable like any other. Addresses nobody "
            "can know in advance are left as TODO placeholders and listed for "
            "you to fill in."
        ),
    )
    rig_init_parser.add_argument(
        "template",
        help="Template name, as `labpilot rig-templates` lists it",
    )
    rig_init_parser.add_argument(
        "--as",
        dest="config_name",
        default="",
        metavar="NAME",
        help="Save it under this name instead of the template's own",
    )
    rig_init_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing config of that name. Refused otherwise: a "
             "config with real addresses typed into it is exactly what you "
             "would not want replaced by placeholders.",
    )
    rig_init_parser.add_argument(
        "--no-activate",
        action="store_true",
        help="Write it without making it the active instrument set",
    )

    # List adapters
    adapters_parser = subparsers.add_parser(
        "list-adapters", help="List all registered instrument adapters"
    )
    adapters_parser.add_argument(
        "--tags",
        type=str,
        nargs="*",
        help="Filter adapters by tags (e.g., --tags camera spectrometer)",
    )
    adapters_parser.add_argument(
        "--format",
        type=str,
        choices=["table", "json", "simple"],
        default="table",
        help="Output format (default: table)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    args = parser.parse_args()

    # Handle subcommands
    if args.command == "app":
        from labpilot.core.launcher import run_app

        sys.exit(run_app(args))
    elif args.command == "start":
        _start_server(args)
    elif args.command == "probe":
        from labpilot.core.probe import probe

        sys.exit(probe(args))
    elif args.command == "rig-templates":
        _list_rig_templates()
    elif args.command == "rig-init":
        sys.exit(_rig_init(args))
    elif args.command == "list-adapters":
        _list_adapters(args)
    else:
        # Default: show help if no arguments
        parser.print_help()


def _log_config(level: str) -> dict:
    """uvicorn's own logging config, with LabPilot's loggers added.

    uvicorn configures handlers for its own loggers and leaves the root one
    alone, so a `logger.warning` from `labpilot` reached stderr only through
    `logging.lastResort` — the bare message, with no level and no timestamp,
    reading like a stray print beside uvicorn's own lines. Routing our
    loggers through uvicorn's `default` handler makes a failed connect look
    like part of the log it is part of.
    """
    import copy

    import uvicorn.config

    config = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    config["loggers"]["labpilot"] = {
        "handlers": ["default"],
        "level": level.upper(),
        "propagate": False,
    }
    return config


def _check_bindable(host: str, port: int) -> None:
    """Fail early, and legibly, when the port cannot be bound.

    uvicorn's own failure for this is an ERROR log line followed by
    "Waiting for application shutdown", which reads like a hang and names
    no remedy. It also calls `sys.exit()` rather than raising, so it
    cannot be caught below — hence a check before it starts.

    The Windows case is worth the message on its own: Hyper-V, WSL2 and
    Docker Desktop reserve blocks of TCP ports at boot, and a bind inside
    one fails with WinError 10013 while nothing is listening there, so
    every "is this port free?" instinct says it is.
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError as exc:
            print(f"❌ Cannot bind {host}:{port} — {exc}", file=sys.stderr)
            if getattr(exc, "winerror", None) == 10013:
                print(
                    "   On Windows this usually means Hyper-V, WSL2 or Docker has\n"
                    "   reserved the port range. Check it with:\n"
                    "     netsh interface ipv4 show excludedportrange protocol=tcp",
                    file=sys.stderr,
                )
            print(
                f"   Try another port:  labpilot start --port {port + 765}\n"
                "   Or let it pick one for you:  labpilot app",
                file=sys.stderr,
            )
            sys.exit(1)


#: Addresses that reach beyond this machine. Binding one is a legitimate
#: thing to want and a dangerous default, so it is allowed and announced.
_EXPOSED_HOSTS = ("0.0.0.0", "::", "")


def _warn_if_exposed(host: str) -> None:
    """Say plainly what binding a public address means here.

    There is no authentication anywhere in the API: anything that can
    reach it can move a stage, open a laser shutter and start a pulse
    sequence. That is acceptable on `127.0.0.1` and is not a thing to
    discover afterwards on a lab network, so the one moment it can be
    said usefully is here.

    `labpilot start` used to default to `0.0.0.0`, which meant every
    headless backend was exposed without anyone choosing it.
    """
    if host not in _EXPOSED_HOSTS:
        return
    print(
        f"⚠️  Binding {host} exposes this backend to the whole network, and\n"
        f"   the API has no authentication: anything that can reach it can\n"
        f"   move a stage, switch a laser on and start a pulse sequence.\n"
        f"   Use --host 127.0.0.1 unless you meant this.",
        file=sys.stderr,
    )


def _start_server(args):
    """Start the LabPilot server."""
    _warn_if_exposed(args.host)
    _check_bindable(args.host, args.port)
    try:
        import uvicorn

        from labpilot.core.server import create_app

        # Prepare configuration directory
        config_dir = None
        if args.config_dir:
            config_dir = Path(args.config_dir)
        elif args.load:
            # Use directory containing the session file
            config_dir = Path(args.load).parent

        # Create FastAPI app
        app = create_app(config_dir)

        # Pre-load session if specified
        if args.load:
            session_path = Path(args.load)
            if not session_path.exists():
                print(f"❌ Session file not found: {session_path}", file=sys.stderr)
                sys.exit(1)

            print(f"🔧 Loading session from: {session_path}")
            # Note: Session loading will be handled by server initialization

        print("🚀 Starting LabPilot server...")
        print(f"   Host: {args.host}")
        print(f"   Port: {args.port}")
        print(f"   Config dir: {config_dir or 'default'}")
        print(f"   Log level: {args.log_level}")
        if args.reload:
            print("   🔄 Auto-reload enabled")

        # Run server
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level=args.log_level,
            log_config=_log_config(args.log_level),
            reload=args.reload,
        )

    except ImportError as e:
        print(f"❌ Missing dependency: {e}", file=sys.stderr)
        print("   Run: pip install 'labpilot-core[server]'", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to start server: {e}", file=sys.stderr)
        sys.exit(1)


def _list_rig_templates() -> None:
    """Print the shipped instrument sets, with what each still needs."""
    from labpilot.core.config.rig_templates import templates

    found = templates()
    if not found:
        print("No rig templates are shipped with this install.")
        return

    print(f"🧰 {len(found)} rig templates\n")
    for template in found:
        print(f"  {template.key}")
        print(f"     {template.description}")
        print(f"     {len(template.devices)} instruments: "
              f"{', '.join(template.adapter_keys)}")
        missing = template.missing_adapters()
        if missing:
            print(f"     ⚠️  not registered here (vendor SDK missing?): "
                  f"{', '.join(missing)}")
        for note in template.todo:
            print(f"     · {note}")
        print()
    print("Install one with:  labpilot rig-init <name>")


def _rig_init(args) -> int:
    """Install a template as the active instrument set."""
    from labpilot.core.config.instrument_sets import InstrumentSetError
    from labpilot.core.config.rig_templates import install

    try:
        path, template = install(
            args.template,
            name=args.config_name,
            activate=not args.no_activate,
            overwrite=args.overwrite,
        )
    except InstrumentSetError as error:
        print(f"❌ {error}", file=sys.stderr)
        return 1

    print(f"✅ Wrote {path}")
    if not args.no_activate:
        print("   It is now the active instrument set.")

    missing = template.missing_adapters()
    if missing:
        # Written anyway: a config is a declaration, and the driver can
        # arrive after it.
        print(
            f"\n⚠️  These did not register on this machine, so they will not "
            f"connect until their vendor SDK is installed:\n"
            f"     {', '.join(missing)}"
        )

    # The notes are prose and say *why*; the detected placeholders are
    # exact. Printing both unfiltered listed `mw.host` twice, so a note
    # that already names a parameter speaks for it.
    notes = list(template.todo)
    silent = [
        f"{identifier}.{key} = {placeholder}"
        for identifier, key, placeholder in template.unresolved()
        if not any(f"{identifier}.{key}" in note for note in notes)
    ]
    if notes or silent:
        print("\n📝 Still to fill in:")
        for line in notes + silent:
            print(f"     {line}")
        print("\n   Edit them in the Devices tab, or in the file above.")

    print("\nThen check the whole rig against its hardware:\n     labpilot probe --all")
    return 0


def _list_adapters(args):
    """List instrument adapters that actually registered on this machine."""
    try:
        from labpilot.instruments import available_catalog
    except ImportError as e:
        print(f"❌ Core components not available: {e}", file=sys.stderr)
        sys.exit(1)

    # available_catalog() rather than INSTRUMENT_CATALOG: only entries whose
    # adapter really registered here, so this lists what can be connected
    # rather than what the static table mentions.
    entries = available_catalog()

    if args.tags:
        wanted = {tag.lower() for tag in args.tags}
        entries = [
            m for m in entries if wanted & {tag.lower() for tag in m.tags}
        ]

    if not entries:
        if args.tags:
            print(f"❌ No adapters found with tags: {', '.join(args.tags)}")
        else:
            print("❌ No adapters found")
        return

    entries = sorted(entries, key=lambda m: m.adapter_key)

    if args.format == "json":
        print(json.dumps([
            {
                "adapter_key": m.adapter_key,
                "manufacturer": m.manufacturer,
                "model": m.model,
                "display_name": m.display_name,
                "instrument_type": m.instrument_type.value,
                "backend": m.backend.value,
                "tags": list(m.tags),
            }
            for m in entries
        ], indent=2))
    elif args.format == "simple":
        for m in entries:
            print(f"{m.adapter_key} ({m.instrument_type.value})")
    else:
        _print_adapters_table(entries, args.tags)


def _print_adapters_table(entries, filter_tags=None):
    """Print catalog entries in table format."""
    suffix = f" (filtered by: {', '.join(filter_tags)})" if filter_tags else ""
    print(f"📦 Found {len(entries)} adapters{suffix}")
    print()

    key_width = max(len(m.adapter_key) for m in entries) + 2
    type_width = max(len(m.instrument_type.value) for m in entries) + 2

    print(f"{'Adapter key':<{key_width}} {'Type':<{type_width}} Tags")
    print("-" * (key_width + type_width + 20))

    for m in entries:
        print(f"{m.adapter_key:<{key_width}} {m.instrument_type.value:<{type_width}} {', '.join(m.tags)}")


if __name__ == "__main__":
    main()
