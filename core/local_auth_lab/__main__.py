from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from core.config import load_config
from core.local_auth_lab.server import LocalAuthLabServer
from core.local_auth_lab.settings import LocalAuthLabSettings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the DICloak local auth lab")
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = LocalAuthLabSettings.from_config(
        load_config(Path(args.config))
    ).ensure_persistent_credentials()
    server = LocalAuthLabServer(settings)
    try:
        server.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    finally:
        server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
