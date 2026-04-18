"""MongoDB migration runner — usage:

    python migrate.py            # apply all pending migrations
    python migrate.py status     # show migration status
    python migrate.py new <name> # create a new migration file
"""
import asyncio
import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from rich.console import Console
from rich.table import Table

load_dotenv()

console = Console()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "irisq_form_builder")
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATIONS_COLLECTION = "_migrations"


def _migration_files():
    return sorted(
        f for f in MIGRATIONS_DIR.iterdir()
        if f.suffix == ".py" and f.name != "__init__.py"
    )


async def _applied(db) -> set:
    docs = await db[MIGRATIONS_COLLECTION].find({}, {"name": 1}).to_list(None)
    return {d["name"] for d in docs}


async def run_migrations():
    client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DATABASE_NAME]

    applied = await _applied(db)
    pending = [f for f in _migration_files() if f.stem not in applied]

    if not pending:
        console.print("[bold green]✓ All migrations already applied.[/bold green]")
        client.close()
        return

    for path in pending:
        name = path.stem
        console.print(f"[yellow]→ Applying {name} …[/yellow]")

        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        await module.up(db)

        await db[MIGRATIONS_COLLECTION].insert_one(
            {"name": name, "applied_at": datetime.utcnow()}
        )
        console.print(f"[green]✓ {name} applied.[/green]")

    console.print("[bold green]All pending migrations applied successfully.[/bold green]")
    client.close()


async def show_status():
    client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DATABASE_NAME]

    applied = await _applied(db)
    files = _migration_files()

    table = Table(title="Migration Status", show_lines=True)
    table.add_column("Migration", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")

    for f in files:
        if f.stem in applied:
            table.add_row(f.stem, "[green]✓ Applied[/green]")
        else:
            table.add_row(f.stem, "[red]✗ Pending[/red]")

    console.print(table)
    client.close()


def create_migration(name: str):
    files = _migration_files()
    nums = [
        int(f.stem.split("_")[0])
        for f in files
        if f.stem != "__init__" and f.stem[0].isdigit()
    ]
    next_num = (max(nums) + 1) if nums else 1
    filename = MIGRATIONS_DIR / f"{next_num:03d}_{name}.py"
    filename.write_text(
        'async def up(db):\n    """Write your migration here."""\n    pass\n'
    )
    console.print(f"[green]✓ Created: {filename.name}[/green]")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "migrate"

    if cmd == "status":
        asyncio.run(show_status())
    elif cmd == "new":
        if len(sys.argv) < 3:
            console.print("[red]Usage: python migrate.py new <migration_name>[/red]")
            sys.exit(1)
        create_migration(sys.argv[2])
    else:
        asyncio.run(run_migrations())
