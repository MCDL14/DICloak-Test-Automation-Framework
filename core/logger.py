from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def setup_logger(config: dict[str, Any]) -> logging.Logger:
    log_config = config.get("log", {})
    log_dir = Path(log_config.get("dir", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    cleanup_old_logs(log_dir, int(log_config.get("keep_days", 14)))

    logger = logging.getLogger("dicloak_automation")
    logger.handlers.clear()
    logger.setLevel(_to_level(log_config.get("level", "INFO")))
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(log_dir / f"run_{timestamp}.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logger.level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logger.level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def cleanup_old_logs(log_dir: Path, keep_days: int) -> None:
    if keep_days <= 0 or not log_dir.exists():
        return
    threshold = datetime.now() - timedelta(days=keep_days)
    for log_file in log_dir.glob("*.log"):
        try:
            if datetime.fromtimestamp(log_file.stat().st_mtime) < threshold:
                log_file.unlink()
        except OSError:
            continue


def _to_level(level_name: str) -> int:
    return getattr(logging, str(level_name).upper(), logging.INFO)
