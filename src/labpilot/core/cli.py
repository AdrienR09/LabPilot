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
  labpilot list-adapters             List all available instrument adapters
  labpilot list-adapters --tags camera   Filter adapters by tags
  labpilot --version                 Show version information
        """,
    )

    # Create subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # The whole application — the cross-platform equivalent of launch.sh
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
        default="0.0.0.0",
        help="Host to bind server to (default: 0.0.0.0)",
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
    elif args.command == "list-adapters":
        _list_adapters(args)
    else:
        # Default: show help if no arguments
        parser.print_help()


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


def _start_server(args):
    """Start the LabPilot server."""
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
            reload=args.reload,
        )

    except ImportError as e:
        print(f"❌ Missing dependency: {e}", file=sys.stderr)
        print("   Run: pip install 'labpilot-core[server]'", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to start server: {e}", file=sys.stderr)
        sys.exit(1)


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
