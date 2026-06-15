from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class DiffCell:
    column: str
    left_value: str
    right_value: str


@dataclass
class RowDiff:
    key_values: dict[str, str]
    diffs: list[DiffCell] = field(default_factory=list)


@dataclass
class ReconcileResult:
    left_only: list[dict[str, str]]
    right_only: list[dict[str, str]]
    row_diffs: list[RowDiff]
    matched_count: int = 0
    left_total: int = 0
    right_total: int = 0


def _read_csv(path: Path, encoding: str = "utf-8") -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, encoding=encoding, keep_default_na=False)
    df.columns = df.columns.str.strip()
    return df


def _make_key_series(df: pd.DataFrame, key_columns: list[str]) -> pd.Series:
    return df[key_columns].astype(str).agg("||".join, axis=1)


def reconcile(
    left_path: Path,
    right_path: Path,
    key_columns: list[str],
    compare_columns: list[str] | None = None,
    encoding: str = "utf-8",
) -> ReconcileResult:
    left_df = _read_csv(left_path, encoding)
    right_df = _read_csv(right_path, encoding)

    for col in key_columns:
        if col not in left_df.columns:
            raise ValueError(f"左表缺少关键字段: {col}")
        if col not in right_df.columns:
            raise ValueError(f"右表缺少关键字段: {col}")

    if compare_columns is None:
        compare_columns = [
            c for c in left_df.columns if c not in key_columns and c in right_df.columns
        ]
    else:
        for col in compare_columns:
            if col not in left_df.columns:
                raise ValueError(f"左表缺少比较字段: {col}")
            if col not in right_df.columns:
                raise ValueError(f"右表缺少比较字段: {col}")

    left_key = _make_key_series(left_df, key_columns)
    right_key = _make_key_series(right_df, key_columns)

    left_key_set = set(left_key)
    right_key_set = set(right_key)

    left_only_mask = ~left_key.isin(right_key_set)
    right_only_mask = ~right_key.isin(left_key_set)

    left_only = left_df.loc[left_only_mask].to_dict("records")
    right_only = right_df.loc[right_only_mask].to_dict("records")

    common_keys = left_key_set & right_key_set

    left_indexed = left_df.copy()
    left_indexed["_key"] = left_key
    left_indexed = left_indexed.set_index("_key")

    right_indexed = right_df.copy()
    right_indexed["_key"] = right_key
    right_indexed = right_indexed.set_index("_key")

    row_diffs: list[RowDiff] = []
    matched_count = 0

    for k in sorted(common_keys):
        left_rows = left_indexed.loc[[k]]
        right_rows = right_indexed.loc[[k]]

        left_row = left_rows.iloc[0]
        right_row = right_rows.iloc[0]

        diffs: list[DiffCell] = []
        for col in compare_columns:
            lv = str(left_row[col]).strip()
            rv = str(right_row[col]).strip()
            if lv != rv:
                diffs.append(DiffCell(column=col, left_value=lv, right_value=rv))

        key_values = {c: str(left_row[c]).strip() for c in key_columns}

        if diffs:
            row_diffs.append(RowDiff(key_values=key_values, diffs=diffs))
        else:
            matched_count += 1

    return ReconcileResult(
        left_only=left_only,
        right_only=right_only,
        row_diffs=row_diffs,
        matched_count=matched_count,
        left_total=len(left_df),
        right_total=len(right_df),
    )
