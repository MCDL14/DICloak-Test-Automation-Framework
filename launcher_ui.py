"""Reserved launcher UI entry point.

The first version uses run.py as the command-line entry point. A desktop
launcher can be added here later without changing the core runner.
"""


def main() -> int:
    print("Launcher UI is reserved for a later version. Use run.py for now.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
