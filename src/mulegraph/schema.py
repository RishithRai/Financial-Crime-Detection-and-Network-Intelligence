"""Versioned schema resources and safely quoted PostgreSQL identifiers."""

import hashlib
import re
from importlib.resources import files

import psycopg
from psycopg import sql


def statement(template: str, schema: str) -> sql.Composed:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,48}", schema):
        raise ValueError(
            "Schema must be a lowercase identifier of at most 49 characters"
        )
    return sql.SQL(template).format(
        core=sql.Identifier(schema),
        labels=sql.Identifier(schema + "_labels"),
    )


def sql_file(name: str) -> str:
    return files("mulegraph").joinpath("sql", name).read_text(encoding="utf-8")


def initialize_schema(connection: psycopg.Connection, schema: str) -> None:
    """Apply version 1 atomically; refuse unknown or edited migration definitions."""
    definition = sql_file("schema.sql")
    digest = hashlib.sha256(definition.encode()).hexdigest()
    existing = connection.execute(
        "SELECT to_regclass(%s)",
        (schema + ".schema_version",),
    ).fetchone()[0]
    if existing is not None:
        versions = connection.execute(
            statement(
                "SELECT version, definition_sha256 FROM {core}.schema_version",
                schema,
            )
        ).fetchall()
        if versions != [(1, digest)]:
            raise ValueError(
                "Database schema version differs; an explicit migration is required"
            )
        return
    connection.execute(statement(definition, schema))
    connection.execute(
        statement(
            "INSERT INTO {core}.schema_version VALUES (1, %s)",
            schema,
        ),
        (digest,),
    )
