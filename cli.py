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
    """Register CLI subcommands.

    Note: subparsers is the parent parser for 'mempalace' that was
    already created by main.py. We add our subcommands to it and set
    mempalace_command as the default handler.
    """
    sub = subparsers.add_subparsers(dest="mempalace_cmd", help="MemPalace commands")

    sub.add_parser("setup", help="Interactive setup wizard")
    sub.add_parser("status", help="Show palace overview")
    sub.add_parser("enable", help="Enable MemPalace in config")
    sub.add_parser("disable", help="Disable MemPalace in config")
    sub.add_parser("summarize", help="Summarize palace contents")

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

    memories_parser = sub.add_parser("memories", help="List all stored memories")
    memories_parser.add_argument("--wing", help="Filter by wing")
    memories_parser.add_argument(
        "--limit", type=int, default=50, help="Max memories to show"
    )

    wings_parser = sub.add_parser("wings", help="List all wings and their rooms")

    profile_sub = sub.add_subparsers(
        dest="mempalace_profile_cmd", help="Profile commands"
    )
    profile_sub.add_parser("list", help="List all profiles with drawer counts")

    profile_create = profile_sub.add_parser("create", help="Create a new profile")
    profile_create.add_argument("name", help="Profile name")

    profile_switch = profile_sub.add_parser("switch", help="Switch to a profile")
    profile_switch.add_argument("name", help="Profile name")

    profile_delete = profile_sub.add_parser("delete", help="Delete a profile")
    profile_delete.add_argument("name", help="Profile name")
    profile_delete.add_argument(
        "--force", action="store_true", help="Skip confirmation"
    )

    subparsers.set_defaults(func=mempalace_command)


def mempalace_command(args) -> int:
    """Main entry point for hermes mempalace command."""
    from hermes_cli.config import load_config

    cmd = getattr(args, "mempalace_cmd", None)
    profile_cmd = getattr(args, "mempalace_profile_cmd", None)
    config = load_config()

    if cmd == "setup":
        return cmd_setup(args, config)
    elif cmd == "status":
        return cmd_status(args)
    elif cmd == "enable":
        return cmd_enable(args, config)
    elif cmd == "disable":
        return cmd_disable(args, config)
    elif cmd == "init":
        return cmd_init(args)
    elif cmd == "mine":
        return cmd_mine(args)
    elif cmd == "memories":
        return cmd_memories(args)
    elif cmd == "wings":
        return cmd_wings(args)
    elif cmd == "summarize":
        return cmd_summarize(args)
    elif profile_cmd:
        return cmd_profile(args, profile_cmd, config)
    else:
        print(
            "Usage: hermes mempalace {setup,status,init,mine,memories,wings,enable,disable,summarize}"
        )
        return 1


def cmd_profile(args, profile_cmd, config) -> int:
    """Handle profile subcommands."""
    profile_name = getattr(args, "name", None)

    if profile_cmd == "list":
        return cmd_profile_list(args, config)
    elif profile_cmd == "create":
        return cmd_profile_create(args, config)
    elif profile_cmd == "switch":
        return cmd_profile_switch(args, config)
    elif profile_cmd == "delete":
        return cmd_profile_delete(args, config)
    else:
        print(f"Usage: hermes mempalace profile {profile_cmd}")
        return 1


def cmd_summarize(args) -> int:
    """Summarize palace contents."""
    try:
        import chromadb
    except ImportError:
        print("ERROR: chromadb not installed")
        return 1

    try:
        from hermes_cli.config import load_config

        hermes_config = load_config()
        mem_cfg = hermes_config.get("memory", {})
        active_profile = mem_cfg.get("active_profile", "default")
        profiles = mem_cfg.get("profiles", {})

        profile_path = profiles.get(active_profile, "~/.mempalace/")
        palace_path = Path(profile_path).expanduser()

        print("=" * 50)
        print("MemPalace Summary")
        print("=" * 50)
        print(f"Active profile: {active_profile}")
        print(f"Palace path: {palace_path}")
        print()

        if not palace_path.exists():
            print("ERROR: Palace not initialized")
            return 1

        chroma_path = palace_path / "palace" / "chroma.sqlite3"
        if not chroma_path.exists():
            print("ERROR: ChromaDB not found")
            return 1

        client = chromadb.PersistentClient(path=str(palace_path / "palace"))
        collection = client.get_or_create_collection("mempalace_drawers")
        count = collection.count()

        print(f"Total drawers: {count}")
        print()

        all_data = collection.get(include=["metadatas"])
        wings = {}
        for m in all_data.get("metadatas") or []:
            w = m.get("wing", "unknown")
            wings[w] = wings.get(w, 0) + 1

        print("Wings:")
        for wing, c in sorted(wings.items(), key=lambda x: -x[1]):
            print(f"  {wing}: {c} drawers")

        print()
        print("Status: OK")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_profile_list(args, config) -> int:
    """List all profiles."""
    try:
        import yaml
        from hermes_cli.config import load_config

        hermes_config = load_config()
        mem_cfg = hermes_config.get("memory", {})
        profiles = mem_cfg.get("profiles", {})
        active = mem_cfg.get("active_profile", "default")

        print("=" * 40)
        print("MemPalace Profiles")
        print("=" * 40)

        if not profiles:
            print("No profiles configured.")
            print("Default: ~/.mempalace/")
            return 0

        print(f"Active: {active}")
        print()

        import sqlite3

        for name, path in profiles.items():
            p = Path(path).expanduser()
            active_mark = " *" if name == active else " "
            if p.exists():
                chroma = p / "palace" / "chroma.sqlite3"
                if chroma.exists():
                    try:
                        count = (
                            sqlite3.connect(str(chroma))
                            .execute("SELECT COUNT(*) FROM embeddings")
                            .fetchone()[0]
                        )
                        print(f"{active_mark} {name}: {path} ({count} drawers)")
                    except Exception:
                        print(f"{active_mark} {name}: {path} (error reading)")
                else:
                    print(f"{active_mark} {name}: {path} (empty)")
            else:
                print(f"{active_mark} {name}: {path} (not created)")

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_profile_create(args, config) -> int:
    """Create a new profile."""
    name = getattr(args, "name", None)
    if not name:
        print("Usage: hermes mempalace profile create <name>")
        return 1

    try:
        import yaml
        from hermes_cli.config import load_config, save_config

        hermes_config = load_config()
        mem_cfg = hermes_config.setdefault("memory", {})
        profiles = mem_cfg.setdefault("profiles", {})

        if name in profiles:
            print(f"Profile '{name}' already exists.")
            return 1

        path = f"~/.mempalace_{name}/"
        profiles[name] = path
        mem_cfg["active_profile"] = name

        save_config(hermes_config)

        profile_dir = Path(path).expanduser()
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "palace").mkdir(parents=True, exist_ok=True)

        print(f"Created profile '{name}' at {path}")
        print(f"Switched to profile '{name}'")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_profile_switch(args, config) -> int:
    """Switch to a profile."""
    name = getattr(args, "name", None)
    if not name:
        print("Usage: hermes mempalace profile switch <name>")
        return 1

    try:
        import yaml
        from hermes_cli.config import load_config, save_config

        hermes_config = load_config()
        mem_cfg = hermes_config.setdefault("memory", {})
        profiles = mem_cfg.setdefault("profiles", {})

        if name not in profiles:
            path = f"~/.mempalace_{name}/"
            profiles[name] = path
        else:
            path = profiles[name]

        profile_dir = Path(path).expanduser()
        if not profile_dir.exists():
            profile_dir.mkdir(parents=True, exist_ok=True)
            (profile_dir / "palace").mkdir(parents=True, exist_ok=True)

        mem_cfg["active_profile"] = name

        save_config(hermes_config)

        print(f"Switched to profile '{name}'")
        print(f"Palace path: {path}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_profile_delete(args, config) -> int:
    """Delete a profile."""
    name = getattr(args, "name", None)
    force = getattr(args, "force", False)

    if not name:
        print("Usage: hermes mempalace profile delete <name>")
        return 1

    if name == "default":
        print("Cannot delete 'default' profile.")
        return 1

    try:
        import yaml
        from hermes_cli.config import load_config, save_config

        hermes_config = load_config()
        mem_cfg = hermes_config.setdefault("memory", {})
        profiles = mem_cfg.setdefault("profiles", {})

        if name not in profiles:
            print(f"Profile '{name}' not found.")
            return 1

        if not force:
            confirm = input(f"Delete profile '{name}'? [y/N]: ").strip().lower()
            if confirm != "y":
                print("Cancelled.")
                return 0

        path = profiles.pop(name)
        profile_dir = Path(path).expanduser()

        if profile_dir.exists():
            import shutil

            shutil.rmtree(profile_dir)

        active = mem_cfg.get("active_profile", "default")
        if active == name:
            mem_cfg["active_profile"] = "default"

        save_config(hermes_config)

        print(f"Deleted profile '{name}'")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_setup(args, config) -> int:
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


def cmd_status(args) -> int:
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

        palace_dir = palace_path  # palace_path already includes /palace
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


def cmd_enable(args, config) -> int:
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


def cmd_disable(args, config) -> int:
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


def cmd_memories(args) -> int:
    """List all stored memories."""
    try:
        from mempalace.config import MempalaceConfig
        import chromadb
    except ImportError:
        print("ERROR: mempalace not installed")
        print("Install: pip install mempalace")
        return 1

    config = MempalaceConfig()
    palace_path = Path(config.palace_path)
    collection_name = config.collection_name
    wing_filter = getattr(args, "wing", None)
    limit = getattr(args, "limit", 50)

    if not palace_path.exists():
        print("ERROR: Palace not initialized. Run: mempalace init <dir>")
        return 1

    try:
        client = chromadb.PersistentClient(path=str(palace_path))
        collection = client.get_collection(collection_name)
        count = collection.count()

        print("=" * 50)
        print("MemPalace Memories")
        print("=" * 50)
        print(f"Total: {count} memories")
        if wing_filter:
            print(f"Filter: wing={wing_filter}")
        print()

        if count == 0:
            print("No memories stored yet.")
            print("Tell Hermes to 'remember' something to add memories.")
            return 0

        all_data = collection.get(include=["documents", "metadatas"])
        docs = all_data.get("documents") or []
        metas = all_data.get("metadatas") or []
        memories = []
        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) else {}
            wing = meta.get("wing", "unknown")
            if wing_filter and wing != wing_filter:
                continue
            room = meta.get("room", "general")
            closet = meta.get("closet", "hall_events")
            memories.append(
                {
                    "doc": doc,
                    "wing": wing,
                    "room": room,
                    "closet": closet,
                }
            )

        for i, mem in enumerate(memories[:limit]):
            print(
                f"{i + 1}. {mem['doc'][:150]}{'...' if len(mem['doc']) > 150 else ''}"
            )
            print(
                f"   Wing: {mem['wing']} | Room: {mem['room']} | Closet: {mem['closet']}"
            )
            print()

        if len(memories) > limit:
            print(f"... and {len(memories) - limit} more memories")
            print(f"Use --limit {len(memories)} to see all")

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_wings(args) -> int:
    """List all wings and their rooms."""
    try:
        from mempalace.config import MempalaceConfig
        import chromadb
    except ImportError:
        print("ERROR: mempalace not installed")
        print("Install: pip install mempalace")
        return 1

    config = MempalaceConfig()
    palace_path = Path(config.palace_path)
    collection_name = config.collection_name

    if not palace_path.exists():
        print("ERROR: Palace not initialized. Run: mempalace init <dir>")
        return 1

    try:
        client = chromadb.PersistentClient(path=str(palace_path))
        collection = client.get_collection(collection_name)
        count = collection.count()

        print("=" * 50)
        print("MemPalace Wings & Rooms")
        print("=" * 50)
        print(f"Total: {count} memories across all wings")
        print()

        if count == 0:
            print("No memories stored yet.")
            return 0

        all_data = collection.get(include=["metadatas"])
        wings = {}
        for meta in all_data.get("metadatas") or []:
            wing = meta.get("wing", "unknown")
            room = meta.get("room", "unknown")
            closet = meta.get("closet", "unknown")

            if wing not in wings:
                wings[wing] = {}
            if room not in wings[wing]:
                wings[wing][room] = {"count": 0, "closets": set()}
            wings[wing][room]["count"] += 1
            wings[wing][room]["closets"].add(closet)

        for wing, rooms in sorted(wings.items()):
            print(f"📁 {wing}")
            total_in_wing = sum(r["count"] for r in rooms.values())
            print(f"   Total: {total_in_wing} memories")
            for room, info in sorted(rooms.items()):
                closets = ", ".join(sorted(info["closets"]))
                print(f"   ├── {room}: {info['count']} memories ({closets})")
            print()

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1
