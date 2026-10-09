"""Errors that carry the exit code the command line returns for them.

Only :func:`inventory_policy_lab.cli.main` turns these exceptions into a
message on stderr and an exit code; the library raises them and never prints.
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_USAGE = 2  # argparse uses 2 for bad options; invalid option values share it
EXIT_INPUT = 3  # the file cannot be opened or decoded
EXIT_DATA = 4  # the file is readable but its content is not valid demand history
EXIT_HISTORY = 5  # valid data, but too few periods for the requested analysis


class InventoryPolicyError(Exception):
    """Base class for every error this package raises on purpose."""

    exit_code = 1


class ConfigError(InventoryPolicyError, ValueError):
    """An analysis setting is out of range (a service level of 1.2, a negative cost)."""

    exit_code = EXIT_USAGE


class InputFileError(InventoryPolicyError):
    """The CSV file is missing, unreadable, or not UTF-8."""

    exit_code = EXIT_INPUT


class DataError(InventoryPolicyError):
    """The CSV is readable but a column is missing or a value is invalid."""

    exit_code = EXIT_DATA


class HistoryError(InventoryPolicyError):
    """The history is too short for the requested holdout."""

    exit_code = EXIT_HISTORY
