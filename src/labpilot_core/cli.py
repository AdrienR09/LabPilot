"""Command-line interface for LabPilot Core.

Provides CLI entry points for launching LabPilot applications and managing the system.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx


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
  labpilot check-ollama              Check Ollama AI service health
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

    # Health check commands
    health_parser = subparsers.add_parser("check-ollama", help="Check Ollama AI service health")
    health_parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )

    # Adapter management commands
    adapters_parser = subparsers.add_parser("list-adapters", help="List available instrument adapters")
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

    # Legacy manager command (kept for backward compatibility)
    parser.add_argument(
        "-manager",
        action="store_true",
        help="Launch the instrument and interface manager GUI (legacy)",
    )

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="Path to lab configuration TOML file (legacy)",
        default=None,
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    args = parser.parse_args()

    # Handle legacy -manager flag
    if args.manager:
        from labpilot_core.gui.main_window import main as gui_main

        sys.argv = [sys.argv[0]]  # Reset argv to only program name for Qt
        if args.config:
            sys.argv.extend(["-c", args.config])
        gui_main()
        return

    # Handle subcommands
    if args.command == "start":
        _start_server(args)
    elif args.command == "check-ollama":
        asyncio.run(_check_ollama(args))
    elif args.command == "list-adapters":
        _list_adapters(args)
    else:
        # Default: show help if no arguments
        parser.print_help()


def _start_server(args):
    """Start the LabPilot server."""
    try:
        import uvicorn

        from labpilot_core.server import create_app

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


async def _check_ollama(args):
    """Check Ollama AI service health."""
    print(f"🔍 Checking Ollama health at {args.base_url}...")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check if Ollama is running
            response = await client.get(f"{args.base_url}/api/tags")

            if response.status_code == 200:
                models = response.json().get("models", [])
                print(f"✅ Ollama is running ({len(models)} models available)")

                # Check for recommended models
                model_names = [m.get("name", "") for m in models]
                recommended = ["mistral", "llama3.1", "qwen2.5-coder"]
                available_recommended = [name for name in recommended if any(name in m for m in model_names)]

                if available_recommended:
                    print(f"   📦 Recommended models: {', '.join(available_recommended)}")
                else:
                    print("   ⚠️  No recommended models found")
                    print("   💡 Install with: ollama pull mistral")

                # List all models
                if models:
                    print("   📋 Available models:")
                    for model in models:
                        name = model.get("name", "unknown")
                        size = model.get("size", 0)
                        size_gb = round(size / (1024**3), 2) if size else 0
                        print(f"      • {name} ({size_gb} GB)")

            else:
                print(f"❌ Ollama API returned status {response.status_code}")
                sys.exit(1)

    except httpx.ConnectError:
        print(f"❌ Cannot connect to Ollama at {args.base_url}")
        print("   💡 Make sure Ollama is running: ollama serve")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        sys.exit(1)


def _list_adapters(args):
    """List available instrument adapters."""
    try:
        from labpilot_core.adapters import AdapterRegistry

        print("🔍 Discovering instrument adapters...")
        registry = AdapterRegistry()

        # Get all adapters
        all_adapters = registry.list_adapters()

        # Filter by tags if specified
        adapters = all_adapters
        if args.tags:
            adapters = []
            for adapter in all_adapters:
                adapter_tags = [tag.lower() for tag in adapter.get("tags", [])]
                if any(tag.lower() in adapter_tags for tag in args.tags):
                    adapters.append(adapter)

        if not adapters:
            if args.tags:
                print(f"❌ No adapters found with tags: {', '.join(args.tags)}")
            else:
                print("❌ No adapters found")
            return

        # Output in requested format
        if args.format == "json":
            print(json.dumps(adapters, indent=2))
        elif args.format == "simple":
            for adapter in adapters:
                print(f"{adapter['name']} ({adapter['type']})")
        else:  # table format
            _print_adapters_table(adapters, args.tags)

    except ImportError as e:
        print(f"❌ Core components not available: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to list adapters: {e}", file=sys.stderr)
        sys.exit(1)


def _print_adapters_table(adapters, filter_tags=None):
    """Print adapters in table format."""
    print(f"📦 Found {len(adapters)} adapters" + (f" (filtered by: {', '.join(filter_tags)})" if filter_tags else ""))
    print()

    # Calculate column widths
    name_width = max(len(adapter["name"]) for adapter in adapters) + 2
    type_width = max(len(adapter["type"]) for adapter in adapters) + 2

    # Print header
    print(f"{'Name':<{name_width}} {'Type':<{type_width}} Tags")
    print("-" * (name_width + type_width + 20))

    # Print adapters
    for adapter in sorted(adapters, key=lambda x: x["name"]):
        name = adapter["name"]
        adapter_type = adapter["type"]
        tags = ", ".join(adapter.get("tags", []))

        print(f"{name:<{name_width}} {adapter_type:<{type_width}} {tags}")


if __name__ == "__main__":
    main()
