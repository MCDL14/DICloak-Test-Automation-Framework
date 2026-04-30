from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.config import ConfigError, load_config
from core.logger import setup_logger
from core.runner import AutomationRunner, ExitCode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dicloak automation runner")
    parser.add_argument("--config", default="config/config.yaml", help="Path to YAML config file")
    parser.add_argument("--level", default=None, help="Case level, for example P0 or P1")
    parser.add_argument("--module", default=None, help="Run cases from one module")
    parser.add_argument(
        "--business-module",
        default=None,
        help="Run cases from one business module, for example 环境管理, 代理管理, 扩展管理, 环境分组管理, 成员管理, 全局设置",
    )
    parser.add_argument("--case", default=None, help="Run one unittest case by name")
    parser.add_argument("--precheck", action="store_true", help="Only run environment precheck")
    parser.add_argument(
        "--attach-existing-app",
        action="store_true",
        help="Debug mode: connect to an already running Dicloak APP and skip APP startup/shutdown",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(Path(args.config))
    except ConfigError as exc:
        print(f"Config error: {exc}")
        return ExitCode.CONFIG_OR_PRECHECK_ERROR

    logger = setup_logger(config)
    runner = AutomationRunner(config=config, logger=logger)

    try:
        if args.precheck:
            return runner.run_precheck_only()
        return runner.run(
            level=args.level,
            module=args.module,
            business_module=args.business_module,
            case=args.case,
            attach_existing_app=args.attach_existing_app,
        )
    except KeyboardInterrupt:
        logger.warning("Run interrupted by user")
        return ExitCode.USER_INTERRUPTED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
