"""Opt-in smoke test against a real PostgreSQL instance."""

import os

import pytest

from mulegraph.db import check_connection


@pytest.mark.integration
def test_postgres_connection():
    database_url = os.environ.get("MULEGRAPH_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set MULEGRAPH_TEST_DATABASE_URL to run the PostgreSQL smoke test")
    check_connection(database_url)
