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
  labpilot start                     Start LabPilot server on default port 8000
  labpilot start --port 8765         Start server on port 8765
  labpilot start --load session.json Load specific session configuration
  labpilot list-adapters             List all available instrument adapters
  labpilot list-adapters --tags camera   Filter adapters by tags
  labpilot -manager                  Launch Qt instrument manager GUI (legacy)
  labpilot --version                 Show version information
        """,
    )

    # Create subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

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
    if args.command == "start":
        _start_server(args)
    elif args.command == "list-adapters":
        _list_adapters(args)
    else:
        # Default: show help if no arguments
        parser.print_help()


def _start_server(args):
    """Start the LabPilot server."""
    try:
        import uvicorn

        from core.server import create_app

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
        from instruments import available_catalog
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
