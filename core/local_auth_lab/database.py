from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from core.local_auth_lab.security import hash_password, verify_password


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class UserRecord:
    site_id: str
    username: str
    enabled: bool
    password_hash: str
    password_salt: str


@dataclass(frozen=True)
class SessionRecord:
    site_id: str
    username: str
    jti: str
    token_hash: str
    run_id: str
    issued_at: str
    expires_at: str
    revoked_at: str
    revoke_reason: str


class LocalAuthDatabase:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(site_id, username)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    jti TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    run_id TEXT NOT NULL DEFAULT '',
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT NOT NULL DEFAULT '',
                    revoke_reason TEXT NOT NULL DEFAULT '',
                    UNIQUE(site_id, jti)
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user
                ON sessions(site_id, username);
                CREATE INDEX IF NOT EXISTS idx_sessions_run
                ON sessions(run_id);
                """
            )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def register_user(self, site_id: str, username: str, password: str) -> bool:
        salt, password_hash = hash_password(password)
        now = _utc_now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO users(
                        site_id, username, password_hash, password_salt, enabled, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, 1, ?, ?)
                    """,
                    (site_id, username, password_hash, salt, now, now),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    def ensure_user(self, site_id: str, username: str, password: str) -> bool:
        user = self.get_user(site_id, username)
        if user:
            return False
        return self.register_user(site_id, username, password)

    def get_user(self, site_id: str, username: str) -> UserRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT site_id, username, enabled, password_hash, password_salt
                FROM users WHERE site_id=? AND username=?
                """,
                (site_id, username),
            ).fetchone()
        if row is None:
            return None
        return UserRecord(
            site_id=str(row["site_id"]),
            username=str(row["username"]),
            enabled=bool(row["enabled"]),
            password_hash=str(row["password_hash"]),
            password_salt=str(row["password_salt"]),
        )

    def authenticate(self, site_id: str, username: str, password: str) -> UserRecord | None:
        user = self.get_user(site_id, username)
        if not user or not user.enabled:
            return None
        if not verify_password(password, user.password_salt, user.password_hash):
            return None
        return user

    def create_session(
        self,
        site_id: str,
        username: str,
        jti: str,
        token_hash: str,
        run_id: str,
        issued_at: str,
        expires_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions(
                    site_id, username, jti, token_hash, run_id, issued_at, expires_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (site_id, username, jti, token_hash, run_id, issued_at, expires_at),
            )

    def get_session(self, site_id: str, jti: str) -> SessionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT site_id, username, jti, token_hash, run_id, issued_at, expires_at,
                       revoked_at, revoke_reason
                FROM sessions WHERE site_id=? AND jti=?
                """,
                (site_id, jti),
            ).fetchone()
        if row is None:
            return None
        return SessionRecord(**{key: str(row[key]) for key in row.keys()})

    def revoke_session(self, site_id: str, jti: str, reason: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions SET revoked_at=?, revoke_reason=?
                WHERE site_id=? AND jti=? AND revoked_at=''
                """,
                (_utc_now(), reason, site_id, jti),
            )
        return cursor.rowcount > 0

    def cleanup(
        self,
        site_id: str = "",
        username: str = "",
        run_id: str = "",
        jti: str = "",
    ) -> dict[str, int]:
        clauses: list[str] = []
        params: list[str] = []
        for column, value in (
            ("site_id", site_id),
            ("username", username),
            ("run_id", run_id),
            ("jti", jti),
        ):
            if value:
                clauses.append(f"{column}=?")
                params.append(value)
        if not clauses:
            raise ValueError("cleanup requires site_id, username, run_id, or jti")
        where = " AND ".join(clauses)
        with self._connect() as connection:
            session_cursor = connection.execute(f"DELETE FROM sessions WHERE {where}", params)
            user_count = 0
            if username and not run_id and not jti:
                user_clauses = [part for part in clauses if not part.startswith(("run_id", "jti"))]
                user_params = [site_id] if site_id else []
                user_params.append(username)
                user_cursor = connection.execute(
                    f"DELETE FROM users WHERE {' AND '.join(user_clauses)}", user_params
                )
                user_count = user_cursor.rowcount
        return {"sessions": session_cursor.rowcount, "users": user_count}

    def state_summary(self) -> dict[str, int]:
        with self._connect() as connection:
            users = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            sessions = int(connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
            active_sessions = int(
                connection.execute("SELECT COUNT(*) FROM sessions WHERE revoked_at='' ").fetchone()[0]
            )
        return {"users": users, "sessions": sessions, "activeSessions": active_sessions}

    def backup_to(self, destination: Path) -> None:
        """Create a transactionally consistent SQLite snapshot, including WAL contents."""
        self.initialize()
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(self.path, timeout=5)
        target = sqlite3.connect(destination, timeout=5)
        try:
            source.execute("PRAGMA busy_timeout=5000")
            source.backup(target)
            target.commit()
        finally:
            target.close()
            source.close()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            yield connection
            connection.commit()
        finally:
            connection.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
