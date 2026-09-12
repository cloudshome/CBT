"""
main.py
=======
Master entrypoint for SKY / CBT operations and SDCC collective commands.
"""

import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "collective":
        from core.collective.cli import run_collective_cli
        return run_collective_cli(sys.argv[2:])

    print("SKY Quantitative Platform / Crypto Brain Terminal (CBT)")
    print("Available entry points:")
    print("  python main.py collective <subcommand>  - SDCC Distributed Collective Core")
    print("  uvicorn app:app --port 8000            - Start FastAPI Master Server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
