"""MemPalace CLI commands for Hermes.

Provides: hermes mempalace {setup,status,init,mine,enable,disable}

Usage:
    hermes mempalace setup      # Interactive setup wizard
    hermes mempalace status     # Show palace overview
    hermes mempalace init <dir> # Initialize new palace
    hermes mempalace mine <dir> # Mine data into palace
    hermes mempalace enable     # Enable plugin in config
    hermes mempalace disable    # Disable plugin in config
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def register_cli(subparsers) -> None:
    """Register CLI subcommands."""
    parser = subparsers.add_parser(
        "mempalace",
        help="Manage MemPalace memory plugin",
        description="MemPalace — local-first AI memory with palace structure",
    )
    sub = parser.add_subparsers(dest="mempalace_cmd", help="MemPalace commands")

    sub.add_parser("setup", help="Interactive setup wizard")
    sub.add_parser("status", help="Show palace overview")
    sub.add_parser("enable", help="Enable MemPalace in config")
    sub.add_parser("disable", help="Disable MemPalace in config")

    init_parser = sub.add_parser("init", help="Initialize a new palace")
    init_parser.add_argument(
        "directory",
        nargs="?",
        default="~/.mempalace",
        help="Palace directory (default: ~/.mempalace/)",
    )

    mine_parser = sub.add_parser("mine", help="Mine data into palace")
    mine_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to mine (default: current directory)",
    )
    mine_parser.add_argument(
        "--mode",
        choices=["projects", "convos", "general"],
        default="projects",
        help="Mining mode",
    )
    mine_parser.add_argument("--wing", help="Wing name to tag mined content")


def mempalace_command(args, config) -> int:
    """Main entry point for hermes mempalace command."""
    cmd = getattr(args, "mempalace_cmd", None)

    if cmd == "setup":
        return cmd_setup(config)
    elif cmd == "status":
        return cmd_status()
    elif cmd == "enable":
        return cmd_enable(config)
    elif cmd == "disable":
        return cmd_disable(config)
    elif cmd == "init":
        return cmd_init(args)
    elif cmd == "mine":
        return cmd_mine(args)
    else:
        print("Usage: hermes mempalace {setup,status,init,mine,enable,disable}")
        return 1


def cmd_setup(config) -> int:
    """Interactive setup wizard."""
    print("=" * 60)
    print("MemPalace Setup Wizard")
    print("=" * 60)
    print()

    print("MemPalace is a local-first AI memory system with:")
    print("  - 96.6% recall on LongMemEval benchmark")
    print("  - Palace structure (Wings/Rooms/Closets/Drawers)")
    print("  - AAAK compression (30x lossless)")
    print("  - ChromaDB + SQLite (fully local)")
    print()

    palace_path = input("Palace directory [~/.mempalace/]: ").strip() or "~/.mempalace/"
    collection = (
        input("Collection name [mempalace_drawers]: ").strip() or "mempalace_drawers"
    )
    default_wing = input("Default wing [wing_general]: ").strip() or "wing_general"

    print()
    print("Checking mempalace installation...")
    try:
        import mempalace

        version = getattr(mempalace, "__version__", "unknown")
        print(f"  mempalace {version} installed")
    except ImportError:
        print("  ERROR: mempalace not installed")
        print()
        print("Install with: pip install mempalace")
        return 1

    from hermes_constants import get_hermes_home, display_hermes_home

    hermes_home = get_hermes_home()
    config_path = hermes_home / ".mempalace" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config_data = {
        "palace_path": palace_path,
        "collection_name": collection,
        "default_wing": default_wing,
    }
    config_path.write_text(json.dumps(config_data, indent=2))
    print(f"  Config saved to {config_path}")

    print()
    print("Enabling MemPalace in Hermes config...")
    try:
        from hermes_cli.config import load_config, save_config

        hermes_config = load_config()
        hermes_config.setdefault("memory", {})["provider"] = "mempalace"
        save_config(hermes_config)
        print("  memory.provider = mempalace")
    except Exception as e:
        print(f"  Warning: Could not update config: {e}")
        print("  Manually run: hermes config set memory.provider mempalace")

    print()
    print("Setup complete!")
    print()
    print("Next steps:")
    print(f"  1. Initialize palace: hermes mempalace init {palace_path}")
    print(f"  2. Mine your data: hermes mempalace mine <directory>")
    print("  3. Start using Hermes with memory!")

    return 0


def cmd_status() -> int:
    """Show palace overview."""
    try:
        import chromadb
        from mempalace.config import MempalaceConfig
    except ImportError:
        print("MemPalace not installed. Install with: pip install mempalace")
        return 1

    try:
        from hermes_constants import get_hermes_home

        config = MempalaceConfig()
        palace_path = Path(config.palace_path).expanduser()
        collection_name = config.collection_name

        print("=" * 40)
        print("MemPalace Status")
        print("=" * 40)
        print(f"Palace path: {palace_path}")
        print(f"Collection: {collection_name}")

        palace_dir = palace_path / "palace"
        if not palace_dir.exists():
            print()
            print("ERROR: Palace not initialized")
            print(f"Run: hermes mempalace init {palace_path}")
            return 1

        client = chromadb.PersistentClient(path=str(palace_dir))
        collection = client.get_collection(collection_name)
        count = collection.count()

        print(f"Total drawers: {count}")

        all_data = collection.get(include=["metadatas"])
        wings = {}
        rooms = {}
        for m in all_data.get("metadatas") or []:
            w = m.get("wing", "unknown")
            r = m.get("room", "unknown")
            wings[w] = wings.get(w, 0) + 1
            rooms[r] = rooms.get(r, 0) + 1

        print()
        print("Wings:")
        for wing, c in sorted(wings.items()):
            print(f"  {wing}: {c} drawers")

        print()
        print("Status: OK")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_enable(config) -> int:
    """Enable MemPalace in config."""
    try:
        from hermes_cli.config import load_config, save_config

        hermes_config = load_config()
        hermes_config.setdefault("memory", {})["provider"] = "mempalace"
        save_config(hermes_config)
        print("MemPalace enabled. Run 'hermes' to start using it.")
        return 0
    except Exception as e:
        print(f"Error enabling MemPalace: {e}")
        return 1


def cmd_disable(config) -> int:
    """Disable MemPalace in config."""
    try:
        from hermes_cli.config import load_config, save_config

        hermes_config = load_config()
        current = hermes_config.get("memory", {}).get("provider")
        if current != "mempalace":
            print("MemPalace is not the active memory provider.")
            return 0
        hermes_config.setdefault("memory", {})["provider"] = ""
        save_config(hermes_config)
        print("MemPalace disabled.")
        return 0
    except Exception as e:
        print(f"Error disabling MemPalace: {e}")
        return 1


def cmd_init(args) -> int:
    """Initialize a new palace."""
    directory = Path(args.directory).expanduser().absolute()
    print(f"Initializing palace at {directory}")

    try:
        from mempalace.onboarding import run_onboarding

        run_onboarding(str(directory))
        print(f"Palace initialized at {directory}")
        print()
        print("Next: hermes mempalace mine <directory> to populate memory")
        return 0
    except ImportError:
        print("ERROR: mempalace not installed")
        print("Install: pip install mempalace")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_mine(args) -> int:
    """Mine data into palace."""
    directory = Path(args.directory).expanduser().absolute()
    mode = getattr(args, "mode", "projects")
    wing = getattr(args, "wing", None)

    print(f"Mining {directory} (mode={mode})")

    cmd = [sys.executable, "-m", "mempalace", "mine", str(directory), "--mode", mode]
    if wing:
        cmd.extend(["--wing", wing])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode
    except Exception as e:
        print(f"Error: {e}")
        return 1
