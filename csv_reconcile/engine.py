from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class DiffCell:
    column: str
    left_value: str
    right_value: str
    diff_type: str = "value_mismatch"


@dataclass
class RowDiff:
    key_values: dict[str, str]
    diffs: list[DiffCell] = field(default_factory=list)


@dataclass
class ReconcileSummary:
    left_total: int = 0
    right_total: int = 0
    matched_count: int = 0
    diff_count: int = 0
    left_only_count: int = 0
    right_only_count: int = 0

    @property
    def left_missing_rate(self) -> float:
        return self.left_only_count / self.left_total if self.left_total else 0.0

    @property
    def right_missing_rate(self) -> float:
        return self.right_only_count / self.right_total if self.right_total else 0.0

    @property
    def row_count_diff(self) -> int:
        return self.left_total - self.right_total


@dataclass
class ReconcileResult:
    left_only: list[dict[str, str]]
    right_only: list[dict[str, str]]
    row_diffs: list[RowDiff]
    summary: ReconcileSummary = field(default_factory=ReconcileSummary)


def _normalize_value(s: str) -> str:
    return s.strip().casefold()


def _read_csv(
    path: Path,
    encoding: str = "utf-8",
    chunksize: int | None = None,
    memory_limit_mb: int | None = None,
) -> pd.DataFrame:
    read_kwargs: dict = {
        "dtype": str,
        "encoding": encoding,
        "keep_default_na": False,
    }
    if chunksize is not None:
        read_kwargs["chunksize"] = chunksize

    if memory_limit_mb is not None and chunksize is None:
        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > memory_limit_mb:
            estimated_rows = max(1, int(1000 * memory_limit_mb / max(file_size_mb, 1)))
            read_kwargs["chunksize"] = estimated_rows

    if "chunksize" in read_kwargs:
        chunks: list[pd.DataFrame] = []
        for chunk in pd.read_csv(path, **read_kwargs):  # type: ignore[call-overload]
            chunk.columns = chunk.columns.str.strip()
            chunks.append(chunk)
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    else:
        df = pd.read_csv(path, **read_kwargs)  # type: ignore[call-overload]

    df.columns = df.columns.str.strip()
    return df


def _make_key_series(
    df: pd.DataFrame,
    key_columns: list[str],
    normalize: bool = False,
) -> pd.Series:
    series = df[key_columns].astype(str)
    if normalize:
        series = series.map(_normalize_value)
    return series.agg("||".join, axis=1)


def _make_compare_series(
    series: pd.Series,
    normalize: bool = False,
) -> pd.Series:
    if normalize:
        return series.astype(str).str.strip().str.casefold()
    return series.astype(str).str.strip()


def reconcile(
    left_path: Path,
    right_path: Path,
    key_columns: list[str],
    compare_columns: list[str] | None = None,
    encoding: str = "utf-8",
    normalize: bool = False,
    chunksize: int | None = None,
    memory_limit_mb: int | None = None,
) -> ReconcileResult:
    left_encoding = encoding
    right_encoding = encoding
    if isinstance(encoding, str) and "|" in encoding:
        left_encoding, right_encoding = encoding.split("|", 1)

    left_df = _read_csv(left_path, left_encoding, chunksize, memory_limit_mb)
    right_df = _read_csv(right_path, right_encoding, chunksize, memory_limit_mb)

    if len(left_df) == 0 and len(right_df) == 0:
        return ReconcileResult(
            left_only=[],
            right_only=[],
            row_diffs=[],
            summary=ReconcileSummary(
                left_total=0,
                right_total=0,
                matched_count=0,
                diff_count=0,
                left_only_count=0,
                right_only_count=0,
            ),
        )

    for col in key_columns:
        if col not in left_df.columns:
            raise ValueError(f"\u5de6\u8868\u7f3a\u5c11\u5173\u952e\u5b57\u6bb5: {col}")
        if col not in right_df.columns:
            raise ValueError(f"\u53f3\u8868\u7f3a\u5c11\u5173\u952e\u5b57\u6bb5: {col}")

    if compare_columns is None:
        compare_columns = [
            c for c in left_df.columns if c not in key_columns and c in right_df.columns
        ]
    else:
        for col in compare_columns:
            if col not in left_df.columns:
                raise ValueError(f"\u5de6\u8868\u7f3a\u5c11\u6bd4\u8f83\u5b57\u6bb5: {col}")
            if col not in right_df.columns:
                raise ValueError(f"\u53f3\u8868\u7f3a\u5c11\u6bd4\u8f83\u5b57\u6bb5: {col}")

    if len(left_df) == 0:
        left_only: list[dict[str, str]] = []
        right_only: list[dict[str, str]] = right_df.to_dict("records")
        common_keys: set[str] = set()
        row_diffs: list[RowDiff] = []
        matched_count: int = 0
    elif len(right_df) == 0:
        left_only = left_df.to_dict("records")
        right_only = []
        common_keys = set()
        row_diffs = []
        matched_count = 0
    else:
        left_key = _make_key_series(left_df, key_columns, normalize=normalize)
        right_key = _make_key_series(right_df, key_columns, normalize=normalize)

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

        row_diffs = []
        matched_count = 0

        for k in sorted(common_keys):
            left_rows = left_indexed.loc[[k]]
            right_rows = right_indexed.loc[[k]]

            left_row = left_rows.iloc[0]
            right_row = right_rows.iloc[0]

            diffs: list[DiffCell] = []
            for col in compare_columns:
                lv_raw = str(left_row[col]).strip()
                rv_raw = str(right_row[col]).strip()
                lv_cmp = _normalize_value(lv_raw) if normalize else lv_raw
                rv_cmp = _normalize_value(rv_raw) if normalize else rv_raw
                if lv_cmp != rv_cmp:
                    diffs.append(
                        DiffCell(
                            column=col,
                            left_value=lv_raw,
                            right_value=rv_raw,
                            diff_type="value_mismatch",
                        )
                    )

            key_values = {c: str(left_row[c]).strip() for c in key_columns}

            if diffs:
                row_diffs.append(RowDiff(key_values=key_values, diffs=diffs))
            else:
                matched_count += 1

    summary = ReconcileSummary(
        left_total=len(left_df),
        right_total=len(right_df),
        matched_count=matched_count,
        diff_count=len(row_diffs),
        left_only_count=len(left_only),
        right_only_count=len(right_only),
    )

    return ReconcileResult(
        left_only=left_only,
        right_only=right_only,
        row_diffs=row_diffs,
        summary=summary,
    )


def normalize_csv(
    input_path: Path,
    output_path: Path,
    encoding: str = "utf-8",
) -> None:
    df = _read_csv(input_path, encoding)
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip().str.casefold()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
