"""Thin compatibility wrapper for the refactored backtester.

This module delegates execution to the `backtester_cli` entrypoint so the
logic remains in the `backtester_*` modules (runner, report creation,
config loader). Keeping this file allows backward compatibility for
users who run `python backtester.py`.
"""

import sys


def _main():
    # Delegate to the CLI entrypoint which will parse sys.argv
    from backtester_cli import main
    return main()


if __name__ == '__main__':
    _main()
