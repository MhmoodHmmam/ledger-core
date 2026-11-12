"""Replay the brief's event stream and print the day-by-day report.

    python replay.py
"""

from ledger.core import replay
from ledger.report import render
from ledger.scenario import ACCOUNTS, EVENTS


def main() -> None:
    print(render(replay(ACCOUNTS, EVENTS)))


if __name__ == "__main__":
    main()
