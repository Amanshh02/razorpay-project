"""Shared reading rules for every ledger loader.

The four loaders differ only in their column schema, so the reading
policy lives here in one place rather than being restated four times:

- Everything is read as text (``dtype=str``). IDs are never handed to
  pandas' type inference, which would happily turn ``pay_00001``-style
  keys into floats if a future export used bare digits (CLAUDE.md §9).
- A missing column is a hard error, never a silent fill or rename.
- Dates are parsed with one explicit format and localised to the single
  project timezone from ``config`` (CLAUDE.md §9).
- Amount columns are parsed from text to ``int64`` paise. The ledgers
  are *already* denominated in integer paise per docs/data-model.md, so
  this converts the representation and never rescales the value.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import config

#: The one date format every ledger uses, confirmed in docs/data-model.md.
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class MissingColumnError(ValueError):
    """A ledger CSV lacks a column that docs/data-model.md requires."""


def read_ledger(path, *, columns, date_columns=(), amount_columns=()):
    """Read one ledger CSV under the project's fixed rules.

    Args:
        path: Path to the CSV.
        columns: The documented schema, in the order the loader returns.
        date_columns: Subset of ``columns`` parsed as IST timestamps.
        amount_columns: Subset of ``columns`` parsed as int64 paise.

    Returns:
        A DataFrame holding exactly ``columns``, in that order.

    Raises:
        MissingColumnError: A documented column is absent from the file.
        ValueError: A date or amount value could not be parsed.
    """
    path = Path(path)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)

    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise MissingColumnError(
            f"{path.name} is missing required column(s): {', '.join(missing)}. "
            f"Columns found: {', '.join(frame.columns)}. "
            f"The expected schema is documented in docs/data-model.md."
        )

    # Extra columns beyond the documented schema are dropped rather than
    # carried through, so downstream stages see one stable shape. This is
    # deliberate and documented; it is not a silent rename.
    frame = frame.loc[:, list(columns)].copy()

    for column in date_columns:
        frame[column] = _parse_dates(frame[column], path, column)
    for column in amount_columns:
        frame[column] = _parse_paise(frame[column], path, column)

    return frame


def _parse_dates(values, path, column):
    """Parse one text column with the stated format and localise to IST."""
    try:
        parsed = pd.to_datetime(values, format=DATE_FORMAT)
    except ValueError as exc:
        raise ValueError(
            f"{path.name}: column {column!r} does not match the expected "
            f"date format {DATE_FORMAT!r}: {exc}"
        ) from exc
    return parsed.dt.tz_localize(config.TIMEZONE)


def _parse_paise(values, path, column):
    """Parse one text column of integer paise into int64.

    Never rescales. A value of ``"2311396"`` means 2311396 paise, both
    before and after this call.
    """
    try:
        return values.astype("int64")
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"{path.name}: column {column!r} contains a value that is not an "
            f"integer number of paise: {exc}"
        ) from exc
