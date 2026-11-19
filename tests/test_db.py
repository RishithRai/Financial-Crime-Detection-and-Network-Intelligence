"""Smoke tests that do not require Docker or a running database."""

from unittest.mock import MagicMock, patch

import psycopg
import pytest

from mulegraph import db


def test_connection_check_executes_query_and_closes_connection():
    with patch("mulegraph.db.psycopg.connect") as connect:
        connection = connect.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value = (1,)
        db.check_connection("postgresql://example/test")

    connect.assert_called_once_with("postgresql://example/test", connect_timeout=5)
    connection.execute.assert_called_once_with("SELECT 1")
    connect.return_value.__exit__.assert_called_once()


def test_unexpected_database_response():
    with patch("mulegraph.db.psycopg.connect") as connect:
        connection = connect.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value = None
        with pytest.raises(RuntimeError, match="Unexpected database response"):
            db.check_connection("postgresql://example/test")


def test_cli_requires_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    check = MagicMock()
    monkeypatch.setattr(db, "check_connection", check)
    assert db.main() == 1
    assert "Set DATABASE_URL" in capsys.readouterr().err
    check.assert_not_called()


def test_cli_success(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/test")
    check = MagicMock()
    monkeypatch.setattr(db, "check_connection", check)
    assert db.main() == 0
    check.assert_called_once_with("postgresql://example/test")
    assert "Database connection OK" in capsys.readouterr().out


@pytest.mark.parametrize("error", [psycopg.OperationalError, RuntimeError])
def test_cli_failure_does_not_leak_credentials(monkeypatch, capsys, error):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@example/test")
    monkeypatch.setattr(db, "check_connection", MagicMock(side_effect=error("secret")))
    assert db.main() == 1
    captured = capsys.readouterr()
    assert "Database check failed" in captured.err
    assert "secret" not in captured.out + captured.err
