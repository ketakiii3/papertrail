"""Apply pending SQL migrations from infra/migrations/ in filename order.

`infra/init.sql` only runs when the Postgres volume is created, so schema
changes to an existing database go through numbered migration files
(`infra/migrations/NNN_name.sql`). Applied versions are recorded in
`schema_migrations`; each file runs in its own transaction. Every migration is
also folded into `init.sql` and written to be idempotent, so running it on a
fresh database is a no-op.

Run inside the compose network:
    docker compose run --rm --no-deps \\
        -v "$(pwd)/scripts:/app/scripts" -v "$(pwd)/infra:/app/infra" \\
        api-server python -m scripts.migrate

Or from the host against the loopback-bound Postgres:
    DATABASE_URL=postgresql://papertrail:papertrail@localhost:5432/papertrail \\
        python scripts/migrate.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "infra" / "migrations"
DEFAULT_URL = "postgresql://papertrail:papertrail@localhost:5432/papertrail"


def pending(applied: set[str], migrations_dir: Path) -> list[Path]:
    """Migration files not yet applied, in filename order."""
    return [p for p in sorted(migrations_dir.glob("*.sql")) if p.stem not in applied]


async def migrate(database_url: str, migrations_dir: Path = DEFAULT_DIR, dry_run: bool = False) -> list[str]:
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version TEXT PRIMARY KEY,
                   applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
               )"""
        )
        applied = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
        done: list[str] = []
        for path in pending(applied, migrations_dir):
            print(f"{'would apply' if dry_run else 'applying'} {path.name}")
            if dry_run:
                done.append(path.stem)
                continue
            async with conn.transaction():
                await conn.execute(path.read_text())
                await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", path.stem)
            done.append(path.stem)
        if not done:
            print("schema up to date")
        return done
    finally:
        await conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="List pending migrations without applying them.")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="Migrations directory.")
    args = parser.parse_args(argv)
    url = os.getenv("DATABASE_URL", DEFAULT_URL)
    asyncio.run(migrate(url, args.dir, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
