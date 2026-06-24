from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.config import ConfigError, load_config
from core.logger import setup_logger
from core.run_metadata import cli_run_start_fields, log_run_end, log_run_start
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
    parser.add_argument(
        "--case",
        action="append",
        default=None,
        help="Run one unittest case by name; repeat to run multiple selected cases",
    )
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

    logger = setup_logger(config, reset=True)
    runner = AutomationRunner(config=config, logger=logger)
    log_run_start(logger, **cli_run_start_fields(args))

    try:
        if args.precheck:
            exit_code = runner.run_precheck_only()
        else:
            exit_code = runner.run(
                level=args.level,
                module=args.module,
                business_module=args.business_module,
                case=args.case,
                attach_existing_app=args.attach_existing_app,
            )
        log_run_end(logger, source="CLI", exit_code=exit_code, success=exit_code == ExitCode.SUCCESS)
        return exit_code
    except KeyboardInterrupt:
        logger.warning("Run interrupted by user")
        log_run_end(logger, source="CLI", exit_code=ExitCode.USER_INTERRUPTED, success=False)
        return ExitCode.USER_INTERRUPTED
    except Exception:
        log_run_end(logger, source="CLI", exit_code=1, success=False, error="unhandled_exception")
        raise


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
