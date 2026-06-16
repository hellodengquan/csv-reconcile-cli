from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from csv_reconcile.engine import normalize_csv, reconcile


def _write_csv(tmp: Path, name: str, content: str, encoding: str = "utf-8") -> Path:
    p = tmp / name
    p.write_text(textwrap.dedent(content).lstrip(), encoding=encoding)
    return p


BASIC_LEFT = """\
order_id,item_id,product,quantity,price
1001,A,Widget,10,5.00
1001,B,Gadget,5,12.50
1002,A,Widget,8,5.00
1003,C,Doohickey,3,7.50
1004,A,Widget,15,5.00
1005,D,Thingamajig,2,20.00
"""

BASIC_RIGHT = """\
order_id,item_id,product,quantity,price
1001,A,Widget,10,5.00
1001,B,Gadget,6,12.50
1002,A,Widget,8,5.50
1003,C,Doohickey,3,7.50
1004,A,Widget,15,5.00
1006,E,Whatchamacallit,1,30.00
"""


class TestBasicReconcile:
    def test_matched_count(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        assert result.summary.matched_count == 3

    def test_diff_count(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        assert result.summary.diff_count == 2

    def test_left_only(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        assert result.summary.left_only_count == 1
        assert result.left_only[0]["order_id"] == "1005"

    def test_right_only(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        assert result.summary.right_only_count == 1
        assert result.right_only[0]["order_id"] == "1006"

    def test_diff_detail_fields(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        diff_1001b = next(
            rd for rd in result.row_diffs if rd.key_values["order_id"] == "1001" and rd.key_values["item_id"] == "B"
        )
        assert len(diff_1001b.diffs) == 1
        assert diff_1001b.diffs[0].column == "quantity"
        assert diff_1001b.diffs[0].left_value == "5"
        assert diff_1001b.diffs[0].right_value == "6"
        assert diff_1001b.diffs[0].diff_type == "value_mismatch"

    def test_missing_rates(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        assert result.summary.left_missing_rate == pytest.approx(1 / 6)
        assert result.summary.right_missing_rate == pytest.approx(1 / 6)

    def test_row_count_diff(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        assert result.summary.row_count_diff == 0


class TestColumnOrderMismatch:
    def test_different_column_order_still_matches(self, tmp_path: Path) -> None:
        left_content = """\
order_id,item_id,price,product,quantity
1001,A,5.00,Widget,10
"""
        right_content = """\
item_id,order_id,quantity,product,price
A,1001,10,Widget,5.00
"""
        left = _write_csv(tmp_path, "left.csv", left_content)
        right = _write_csv(tmp_path, "right.csv", right_content)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        assert result.summary.matched_count == 1
        assert result.summary.diff_count == 0


class TestNormalize:
    def test_whitespace_and_case_normalize(self, tmp_path: Path) -> None:
        left_content = """\
order_id,item_id,product,quantity
1001,A, Widget ,10
1002,B,GADGET,5
"""
        right_content = """\
order_id,item_id,product,quantity
1001,a,WIDGET,10
1002,b,gadget,5
"""
        left = _write_csv(tmp_path, "left.csv", left_content)
        right = _write_csv(tmp_path, "right.csv", right_content)
        result = reconcile(
            left,
            right,
            key_columns=["order_id", "item_id"],
            normalize=True,
        )
        assert result.summary.matched_count == 2
        assert result.summary.diff_count == 0

    def test_without_normalize_key_mismatch(self, tmp_path: Path) -> None:
        left_content = """\
order_id,item_id,product
1001,A,Widget
"""
        right_content = """\
order_id,item_id,product
1001,a,Widget
"""
        left = _write_csv(tmp_path, "left.csv", left_content)
        right = _write_csv(tmp_path, "right.csv", right_content)
        result = reconcile(
            left,
            right,
            key_columns=["order_id", "item_id"],
            normalize=False,
        )
        assert result.summary.left_only_count == 1
        assert result.summary.right_only_count == 1

    def test_normalize_value_comparison(self, tmp_path: Path) -> None:
        left_content = """\
order_id,item_id,product
1001,A, Widget
"""
        right_content = """\
order_id,item_id,product
1001,A,WIDGET
"""
        left = _write_csv(tmp_path, "left.csv", left_content)
        right = _write_csv(tmp_path, "right.csv", right_content)
        result = reconcile(
            left,
            right,
            key_columns=["order_id", "item_id"],
            normalize=True,
        )
        assert result.summary.matched_count == 1
        assert result.summary.diff_count == 0


class TestEmptyFiles:
    def test_both_empty(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", "order_id,item_id,product\n")
        right = _write_csv(tmp_path, "right.csv", "order_id,item_id,product\n")
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        assert result.summary.left_total == 0
        assert result.summary.right_total == 0
        assert result.summary.matched_count == 0
        assert result.summary.left_missing_rate == 0.0
        assert result.summary.right_missing_rate == 0.0

    def test_one_empty(self, tmp_path: Path) -> None:
        left_content = """\
order_id,item_id,product
1001,A,Widget
"""
        right = _write_csv(tmp_path, "right.csv", "order_id,item_id,product\n")
        left = _write_csv(tmp_path, "left.csv", left_content)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        assert result.summary.left_only_count == 1
        assert result.summary.right_only_count == 0
        assert result.summary.left_missing_rate == 1.0


class TestEncodingMismatch:
    def test_dual_encoding(self, tmp_path: Path) -> None:
        left_content = "order_id,item_id,product\n1001,A,Widget\n"
        right_content = "order_id,item_id,product\n1001,A,Widget\n"
        left = tmp_path / "left.csv"
        left.write_text(left_content, encoding="utf-8")
        right = tmp_path / "right.csv"
        right.write_text(right_content, encoding="gbk")
        result = reconcile(
            left,
            right,
            key_columns=["order_id", "item_id"],
            encoding="utf-8|gbk",
        )
        assert result.summary.matched_count == 1


class TestMissingColumns:
    def test_missing_key_column_left(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", "item_id,product\nA,Widget\n")
        right = _write_csv(tmp_path, "right.csv", "order_id,item_id,product\n1001,A,Widget\n")
        with pytest.raises(ValueError, match="左表缺少关键字段"):
            reconcile(left, right, key_columns=["order_id", "item_id"])

    def test_missing_compare_column_right(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", "order_id,item_id,product,price\n1001,A,Widget,5.00\n")
        right = _write_csv(tmp_path, "right.csv", "order_id,item_id,product\n1001,A,Widget\n")
        with pytest.raises(ValueError, match="右表缺少比较字段"):
            reconcile(left, right, key_columns=["order_id", "item_id"], compare_columns=["price"])


class TestSingleKeyColumn:
    def test_single_key(self, tmp_path: Path) -> None:
        left_content = """\
order_id,product,price
1001,Widget,5.00
1002,Gadget,12.50
"""
        right_content = """\
order_id,product,price
1001,Widget,5.00
1002,Gadget,13.00
"""
        left = _write_csv(tmp_path, "left.csv", left_content)
        right = _write_csv(tmp_path, "right.csv", right_content)
        result = reconcile(left, right, key_columns=["order_id"])
        assert result.summary.matched_count == 1
        assert result.summary.diff_count == 1


class TestChunkedReading:
    def test_chunksize(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(
            left,
            right,
            key_columns=["order_id", "item_id"],
            chunksize=2,
        )
        assert result.summary.left_total == 6
        assert result.summary.right_total == 6
        assert result.summary.matched_count == 3

    def test_memory_limit(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(
            left,
            right,
            key_columns=["order_id", "item_id"],
            memory_limit_mb=1,
        )
        assert result.summary.left_total == 6
        assert result.summary.right_total == 6


class TestNormalizeCsv:
    def test_normalize_output(self, tmp_path: Path) -> None:
        content = "Name,Value\n Hello ,WORLD\nFOO ,Bar\n"
        inp = _write_csv(tmp_path, "input.csv", content)
        out = tmp_path / "output.csv"
        normalize_csv(inp, out)
        text = out.read_text(encoding="utf-8-sig")
        assert "hello" in text
        assert "world" in text
        assert "foo" in text
        assert "bar" in text
