from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

_FULLWIDTH_PUNCT: dict[int, str] = {
    0xFF01: "!", 0xFF03: "#", 0xFF04: "$", 0xFF05: "%", 0xFF06: "&",
    0xFF08: "(", 0xFF09: ")", 0xFF0A: "*", 0xFF0B: "+", 0xFF0C: ",",
    0xFF0E: ".", 0xFF0F: "/", 0xFF1A: ":", 0xFF1B: ";", 0xFF1C: "<",
    0xFF1D: "=", 0xFF1E: ">", 0xFF1F: "?", 0xFF20: "@", 0xFF3B: "[",
    0xFF3D: "]", 0xFF5B: "{", 0xFF5C: "|", 0xFF5D: "}", 0xFF5E: "~",
}

_CJK_PUNCT_MAP: dict[int, str] = {
    0x3001: ",", 0x3002: ".", 0x300A: "<", 0x300B: ">",
    0x300C: '"', 0x300D: '"', 0x300E: '"', 0x300F: '"',
    0x3010: "[", 0x3011: "]", 0x3014: "(", 0x3015: ")",
    0xFF01: "!", 0xFF08: "(", 0xFF09: ")", 0xFF0C: ",",
    0xFF0E: ".", 0xFF1A: ":", 0xFF1B: ";", 0xFF1F: "?",
}


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
class ColumnMissingRate:
    column: str
    left_missing: int = 0
    right_missing: int = 0
    left_total: int = 0
    right_total: int = 0

    @property
    def left_missing_rate(self) -> float:
        return self.left_missing / self.left_total if self.left_total else 0.0

    @property
    def right_missing_rate(self) -> float:
        return self.right_missing / self.right_total if self.right_total else 0.0


@dataclass
class ReconcileSummary:
    left_total: int = 0
    right_total: int = 0
    matched_count: int = 0
    diff_count: int = 0
    left_only_count: int = 0
    right_only_count: int = 0
    column_missing_rates: list[ColumnMissingRate] = field(default_factory=list)

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


def _fullwidth_to_ascii(s: str) -> str:
    return "".join(_FULLWIDTH_PUNCT.get(ord(c), c) for c in s)


def _cjk_punct_to_ascii(s: str) -> str:
    return "".join(_CJK_PUNCT_MAP.get(ord(c), c) for c in s)


def _normalize_value(s: str) -> str:
    s = s.strip()
    s = _fullwidth_to_ascii(s)
    s = _cjk_punct_to_ascii(s)
    s = unicodedata.normalize("NFC", s)
    return s.casefold()


def _estimate_row_bytes(path: Path, encoding: str = "utf-8") -> int:
    sample_lines: list[str] = []
    with open(path, encoding=encoding, errors="replace") as f:
        for i, line in enumerate(f):
            if i >= 10:
                break
            sample_lines.append(line)
    if not sample_lines:
        return 200
    avg = sum(len(line.encode("utf-8", errors="replace")) for line in sample_lines) / len(sample_lines)
    return max(100, int(avg))


def _adaptive_chunksize(
    path: Path,
    memory_limit_mb: int,
    encoding: str = "utf-8",
) -> int:
    row_bytes = _estimate_row_bytes(path, encoding)
    chunk_rows = max(100, int(memory_limit_mb * 1024 * 1024 / row_bytes / 4))
    return chunk_rows


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
        adaptive = _adaptive_chunksize(path, memory_limit_mb, encoding)
        read_kwargs["chunksize"] = adaptive

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
    secondary_columns: list[str] | None = None,
    normalize: bool = False,
) -> pd.Series:
    primary = df[key_columns].astype(str)
    if normalize:
        primary = primary.map(_normalize_value)
    primary_key = primary.agg("||".join, axis=1)

    if secondary_columns:
        valid_secondary = [c for c in secondary_columns if c in df.columns]
        if valid_secondary:
            secondary = df[valid_secondary].astype(str)
            if normalize:
                secondary = secondary.map(_normalize_value)
            secondary_key = secondary.agg("||".join, axis=1)
            return primary_key + "@@" + secondary_key

    return primary_key


def _make_compare_series(
    series: pd.Series,
    normalize: bool = False,
) -> pd.Series:
    if normalize:
        return series.astype(str).map(_normalize_value)
    return series.astype(str).str.strip()


def _compute_column_missing_rates(
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    left_only_df: pd.DataFrame,
    right_only_df: pd.DataFrame,
    compare_columns: list[str],
) -> list[ColumnMissingRate]:
    rates: list[ColumnMissingRate] = []
    for col in compare_columns:
        left_missing = int(left_only_df[col].isna().sum()) + int((left_only_df[col].astype(str).str.strip() == "").sum()) if col in left_only_df.columns else left_only_df.shape[0]
        right_missing = int(right_only_df[col].isna().sum()) + int((right_only_df[col].astype(str).str.strip() == "").sum()) if col in right_only_df.columns else right_only_df.shape[0]
        rates.append(ColumnMissingRate(
            column=col,
            left_missing=left_missing,
            right_missing=right_missing,
            left_total=len(left_df),
            right_total=len(right_df),
        ))
    return rates


def reconcile(
    left_path: Path,
    right_path: Path,
    key_columns: list[str],
    compare_columns: list[str] | None = None,
    secondary_keys: list[str] | None = None,
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
        left_only_df = left_df.iloc[0:0]
        right_only_df = right_df
    elif len(right_df) == 0:
        left_only = left_df.to_dict("records")
        right_only = []
        common_keys = set()
        row_diffs = []
        matched_count = 0
        left_only_df = left_df
        right_only_df = right_df.iloc[0:0]
    else:
        left_key = _make_key_series(left_df, key_columns, secondary_keys, normalize=normalize)
        right_key = _make_key_series(right_df, key_columns, secondary_keys, normalize=normalize)

        left_key_set = set(left_key)
        right_key_set = set(right_key)

        left_only_mask = ~left_key.isin(right_key_set)
        right_only_mask = ~right_key.isin(left_key_set)

        left_only_df = left_df.loc[left_only_mask]
        right_only_df = right_df.loc[right_only_mask]
        left_only = left_only_df.to_dict("records")
        right_only = right_only_df.to_dict("records")

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

    col_missing_rates = _compute_column_missing_rates(
        left_df, right_df, left_only_df, right_only_df, compare_columns
    )

    summary = ReconcileSummary(
        left_total=len(left_df),
        right_total=len(right_df),
        matched_count=matched_count,
        diff_count=len(row_diffs),
        left_only_count=len(left_only),
        right_only_count=len(right_only),
        column_missing_rates=col_missing_rates,
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
        df[col] = df[col].astype(str).map(_normalize_value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
