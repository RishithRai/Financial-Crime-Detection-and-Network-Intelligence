"""A read-only PostgreSQL connectivity check."""

import os
import sys

import psycopg


def check_connection(database_url: str) -> None:
    """Execute a trivial query, raising an error if connectivity is unhealthy."""
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        row = connection.execute("SELECT 1").fetchone()
        if row != (1,):
            raise RuntimeError("Unexpected database response")


def main() -> int:
    """Check DATABASE_URL without printing credentials or connection details."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Set DATABASE_URL before running the database check.", file=sys.stderr)
        return 1
    try:
        check_connection(database_url)
    except (psycopg.Error, RuntimeError):
        print(
            "Database check failed. Check configuration and PostgreSQL.",
            file=sys.stderr,
        )
        return 1
    print("Database connection OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
