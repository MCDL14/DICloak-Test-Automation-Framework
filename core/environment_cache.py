from __future__ import annotations

import re
import shutil
import stat
from pathlib import Path


ENVIRONMENT_CACHE_DIR_NAME = re.compile(r"^\d{19}$")


def numeric_environment_cache_dirs(cache_dir: Path | str) -> tuple[Path, ...]:
    """Return validated direct child directories whose names are exactly 19 digits."""
    root = _validate_cache_root(cache_dir)
    targets: list[Path] = []
    for candidate in root.iterdir():
        if not ENVIRONMENT_CACHE_DIR_NAME.fullmatch(candidate.name):
            continue
        targets.append(_validate_target(root, candidate))
    return tuple(sorted(targets, key=lambda path: path.name))


def delete_numeric_environment_cache_dirs(cache_dir: Path | str) -> tuple[str, ...]:
    """Delete only validated 19-digit direct child directories and verify their removal."""
    root = _validate_cache_root(cache_dir)
    targets = numeric_environment_cache_dirs(root)

    # Validate the complete target set before the first destructive operation.
    for target in targets:
        _validate_target(root, target)

    deleted_names: list[str] = []
    for target in targets:
        _validate_cache_root(root)
        validated_target = _validate_target(root, target)
        try:
            shutil.rmtree(validated_target)
        except OSError as exc:
            raise RuntimeError(f"environment cache directory could not be deleted: {validated_target}: {exc}") from exc
        if validated_target.exists() or validated_target.is_symlink():
            raise RuntimeError(f"environment cache directory still exists after deletion: {validated_target}")
        deleted_names.append(validated_target.name)

    remaining = {path.name for path in numeric_environment_cache_dirs(root)}
    undeleted = sorted(set(deleted_names) & remaining)
    if undeleted:
        raise RuntimeError(f"environment cache directories still exist after deletion: {undeleted}")
    return tuple(deleted_names)


def _validate_cache_root(cache_dir: Path | str) -> Path:
    raw = Path(cache_dir).expanduser()
    if not raw.is_absolute():
        raise ValueError(f"environment cache directory must be absolute: {raw}")
    try:
        root = raw.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"environment cache directory does not exist: {raw}") from exc
    if root == Path(root.anchor):
        raise ValueError(f"refuse to use a filesystem root as environment cache directory: {root}")
    if _is_link_or_reparse_point(raw) or _is_link_or_reparse_point(root):
        raise ValueError(f"environment cache directory must not be a link or reparse point: {root}")
    if not root.is_dir():
        raise ValueError(f"environment cache path is not a directory: {root}")
    return root


def _validate_target(root: Path, target: Path) -> Path:
    if not ENVIRONMENT_CACHE_DIR_NAME.fullmatch(target.name):
        raise ValueError(f"refuse to delete a non-19-digit cache entry: {target}")
    if _is_link_or_reparse_point(target):
        raise ValueError(f"refuse to delete a linked environment cache directory: {target}")
    try:
        resolved = target.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"environment cache target does not exist: {target}") from exc
    if resolved.parent != root:
        raise ValueError(f"environment cache target escaped the configured cache directory: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"19-digit environment cache entry is not a directory: {resolved}")
    return resolved


def _is_link_or_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    reparse_attribute = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    is_junction = bool(getattr(path, "is_junction", lambda: False)())
    return path.is_symlink() or is_junction or bool(attributes & reparse_attribute)
