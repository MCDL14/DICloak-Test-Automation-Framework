from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.local_auth_lab.database import LocalAuthDatabase, SCHEMA_VERSION
from core.local_auth_lab.security import signing_key_id
from core.local_auth_lab.settings import LOCAL_OVERRIDE_PATH, LocalAuthLabSettings


STATE_MANIFEST_NAME = ".local_auth_lab_state.json"


@dataclass(frozen=True)
class LocalAuthLabStateBundle:
    archive_path: Path
    signing_key_id: str
    database_sha256: str
    users: int
    sessions: int
    relative_override_path: str
    relative_credentials_path: str
    relative_database_path: str


def create_state_bundle(
    config: dict[str, Any],
    project_root: Path | str,
) -> LocalAuthLabStateBundle:
    """Package persistent credentials and a consistent DB snapshot for one remote node."""
    root = Path(project_root).resolve()
    settings = LocalAuthLabSettings.from_config(config).ensure_persistent_credentials()
    settings.validate_for_start()

    override_path = root / LOCAL_OVERRIDE_PATH
    if not override_path.is_file():
        raise ValueError(f"local auth lab override is missing: {override_path}")

    override_rel = _project_relative(root, override_path)
    credentials_rel = _project_relative(root, settings.credentials_path)
    database_rel = _project_relative(root, settings.database_path)

    fd, raw_archive_path = tempfile.mkstemp(prefix="dicloak_auth_state_", suffix=".tar.gz")
    os.close(fd)
    archive_path = Path(raw_archive_path)
    with tempfile.TemporaryDirectory(prefix="dicloak_auth_db_") as raw_temp_dir:
        snapshot_path = Path(raw_temp_dir) / "auth.db"
        database = LocalAuthDatabase(settings.database_path)
        database.backup_to(snapshot_path)
        summary = database.state_summary()
        database_sha256 = _file_sha256(snapshot_path)
        manifest = {
            "schema": 1,
            "database_schema": SCHEMA_VERSION,
            "created_at_epoch": int(time.time()),
            "signing_key_id": signing_key_id(settings.signing_secret),
            "database_sha256": database_sha256,
            "users": summary["users"],
            "sessions": summary["sessions"],
            "paths": {
                "override": override_rel,
                "credentials": credentials_rel,
                "database": database_rel,
            },
        }
        manifest_bytes = json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        try:
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.add(override_path, arcname=override_rel, recursive=False)
                archive.add(settings.credentials_path, arcname=credentials_rel, recursive=False)
                archive.add(snapshot_path, arcname=database_rel, recursive=False)
                info = tarfile.TarInfo(STATE_MANIFEST_NAME)
                info.size = len(manifest_bytes)
                info.mtime = time.time()
                info.mode = 0o600
                archive.addfile(info, io.BytesIO(manifest_bytes))
        except Exception:
            try:
                archive_path.unlink()
            except OSError:
                pass
            raise

    return LocalAuthLabStateBundle(
        archive_path=archive_path,
        signing_key_id=manifest["signing_key_id"],
        database_sha256=database_sha256,
        users=summary["users"],
        sessions=summary["sessions"],
        relative_override_path=override_rel,
        relative_credentials_path=credentials_rel,
        relative_database_path=database_rel,
    )


def _project_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"local auth lab state path must stay inside project root: {path}") from exc


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
