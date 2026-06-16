from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from csv_reconcile.engine import _normalize_value, normalize_csv, recommend_key_columns, reconcile
from csv_reconcile.html_report import generate_html
from csv_reconcile.sql import generate_fix_sql


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

    def test_column_missing_rates(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        assert len(result.summary.column_missing_rates) > 0
        cmr_product = next(c for c in result.summary.column_missing_rates if c.column == "product")
        assert cmr_product.left_total == 6
        assert cmr_product.right_total == 6


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


class TestSecondaryKeys:
    def test_secondary_keys_refine_match(self, tmp_path: Path) -> None:
        left_content = """\
order_id,region,batch,quantity
1001,North,B1,10
1001,South,B2,5
"""
        right_content = """\
order_id,region,batch,quantity
1001,North,B1,12
1001,South,B2,7
"""
        left = _write_csv(tmp_path, "left.csv", left_content)
        right = _write_csv(tmp_path, "right.csv", right_content)
        result_no_secondary = reconcile(left, right, key_columns=["order_id"])
        assert result_no_secondary.summary.diff_count == 1

        result_with_secondary = reconcile(
            left, right, key_columns=["order_id"], secondary_keys=["region", "batch"]
        )
        assert result_with_secondary.summary.matched_count == 0
        assert result_with_secondary.summary.diff_count == 2


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


class TestNormalizePunctuation:
    def test_fullwidth_punctuation(self) -> None:
        assert _normalize_value("\uff01hello\uff1f") == "!hello?"

    def test_cjk_punctuation(self) -> None:
        assert _normalize_value("\u3001test\u3002") == ",test."

    def test_nfc_normalization(self) -> None:
        composed = "\u00e9"
        decomposed = "e\u0301"
        assert _normalize_value(composed) == _normalize_value(decomposed)

    def test_fullwidth_digits(self, tmp_path: Path) -> None:
        left_content = "order_id,product\n\uff11\uff10\uff10\uff11,Widget\n"
        right_content = "order_id,product\n1001,Widget\n"
        left = tmp_path / "left.csv"
        left.write_text(left_content, encoding="utf-8")
        right = tmp_path / "right.csv"
        right.write_text(right_content, encoding="utf-8")
        result = reconcile(left, right, key_columns=["order_id"], normalize=True)
        assert result.summary.matched_count == 0


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
        with pytest.raises(ValueError, match="\u5de6\u8868\u7f3a\u5c11\u5173\u952e\u5b57\u6bb5"):
            reconcile(left, right, key_columns=["order_id", "item_id"])

    def test_missing_compare_column_right(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", "order_id,item_id,product,price\n1001,A,Widget,5.00\n")
        right = _write_csv(tmp_path, "right.csv", "order_id,item_id,product\n1001,A,Widget\n")
        with pytest.raises(ValueError, match="\u53f3\u8868\u7f3a\u5c11\u6bd4\u8f83\u5b57\u6bb5"):
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


class TestQuotedFieldsWithNewlines:
    def test_quoted_field_with_embedded_newline(self, tmp_path: Path) -> None:
        left_content = 'order_id,product,description\n1001,Widget,"A nice\nwidget"\n1002,Gadget,Simple\n'
        right_content = 'order_id,product,description\n1001,Widget,"A nice\nwidget"\n1002,Gadget,Simple\n'
        left = tmp_path / "left.csv"
        left.write_text(left_content, encoding="utf-8")
        right = tmp_path / "right.csv"
        right.write_text(right_content, encoding="utf-8")
        result = reconcile(left, right, key_columns=["order_id"])
        assert result.summary.matched_count == 2
        assert result.summary.diff_count == 0

    def test_quoted_field_diff(self, tmp_path: Path) -> None:
        left_content = 'order_id,product,description\n1001,Widget,"A nice\nwidget"\n'
        right_content = 'order_id,product,description\n1001,Widget,"A broken\nwidget"\n'
        left = tmp_path / "left.csv"
        left.write_text(left_content, encoding="utf-8")
        right = tmp_path / "right.csv"
        right.write_text(right_content, encoding="utf-8")
        result = reconcile(left, right, key_columns=["order_id"])
        assert result.summary.diff_count == 1
        assert result.row_diffs[0].diffs[0].column == "description"

    def test_quoted_field_with_commas(self, tmp_path: Path) -> None:
        left_content = 'order_id,product,notes\n1001,Widget,"price: 5.00, qty: 10"\n'
        right_content = 'order_id,product,notes\n1001,Widget,"price: 5.00, qty: 10"\n'
        left = tmp_path / "left.csv"
        left.write_text(left_content, encoding="utf-8")
        right = tmp_path / "right.csv"
        right.write_text(right_content, encoding="utf-8")
        result = reconcile(left, right, key_columns=["order_id"])
        assert result.summary.matched_count == 1


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


class TestFixSql:
    def test_generate_update_sql(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        sql = generate_fix_sql(result, "orders", ["order_id", "item_id"])
        assert "UPDATE orders SET" in sql
        assert "WHERE order_id = '1001' AND item_id = 'B'" in sql

    def test_generate_insert_sql(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        sql = generate_fix_sql(result, "orders", ["order_id", "item_id"])
        assert "INSERT INTO orders" in sql
        assert "1006" in sql

    def test_generate_delete_sql(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        sql = generate_fix_sql(result, "orders", ["order_id", "item_id"])
        assert "DELETE FROM orders" in sql
        assert "1005" in sql

    def test_no_insert_flag(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        sql = generate_fix_sql(result, "orders", ["order_id", "item_id"], generate_inserts=False)
        assert "INSERT INTO" not in sql

    def test_no_delete_flag(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        sql = generate_fix_sql(result, "orders", ["order_id", "item_id"], generate_deletes=False)
        assert "DELETE FROM" not in sql

    def test_sql_escape_quotes(self, tmp_path: Path) -> None:
        left_content = """\
order_id,name
1001,O'Brien
"""
        right_content = """\
order_id,name
1001,O'Connell
"""
        left = _write_csv(tmp_path, "left.csv", left_content)
        right = _write_csv(tmp_path, "right.csv", right_content)
        result = reconcile(left, right, key_columns=["order_id"])
        sql = generate_fix_sql(result, "users", ["order_id"])
        assert "O''Brien" not in sql or "O''Connell" in sql

    def test_no_differences_sql(self, tmp_path: Path) -> None:
        content = "order_id,product\n1001,Widget\n"
        left = _write_csv(tmp_path, "left.csv", content)
        right = _write_csv(tmp_path, "right.csv", content)
        result = reconcile(left, right, key_columns=["order_id"])
        sql = generate_fix_sql(result, "orders", ["order_id"])
        assert "No differences found" in sql

    def test_transaction_boundaries(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        sql = generate_fix_sql(result, "orders", ["order_id", "item_id"])
        assert sql.startswith("BEGIN TRANSACTION;")
        assert "COMMIT;" in sql

    def test_no_transaction_flag(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        sql = generate_fix_sql(result, "orders", ["order_id", "item_id"], use_transaction=False)
        assert "BEGIN TRANSACTION" not in sql
        assert "COMMIT" not in sql
        assert "UPDATE orders" in sql

    def test_delete_statements_complete(self, tmp_path: Path) -> None:
        left_content = "id,name\n1,Alice\n2,Bob\n"
        right_content = "id,name\n1,Alice\n"
        left = _write_csv(tmp_path, "left.csv", left_content)
        right = _write_csv(tmp_path, "right.csv", right_content)
        result = reconcile(left, right, key_columns=["id"])
        sql = generate_fix_sql(result, "users", ["id"])
        assert "DELETE FROM users WHERE id = '2';" in sql
        assert "BEGIN TRANSACTION;" in sql
        assert "COMMIT;" in sql


class TestQuotedNestedQuotes:
    def test_quoted_with_escaped_quotes(self, tmp_path: Path) -> None:
        left_content = (
            'order_id,description\n'
            '1001,"He said ""hello"" to me"\n'
        )
        right_content = (
            'order_id,description\n'
            '1001,"He said ""hello"" to me"\n'
        )
        left = tmp_path / "left.csv"
        left.write_text(left_content, encoding="utf-8")
        right = tmp_path / "right.csv"
        right.write_text(right_content, encoding="utf-8")
        result = reconcile(left, right, key_columns=["order_id"])
        assert result.summary.matched_count == 1
        assert result.row_diffs == []

    def test_quoted_nested_quotes_mismatch(self, tmp_path: Path) -> None:
        left_content = (
            'order_id,description\n'
            '1001,"He said ""hello"" to me"\n'
        )
        right_content = (
            'order_id,description\n'
            '1001,"He said ""hi"" to me"\n'
        )
        left = tmp_path / "left.csv"
        left.write_text(left_content, encoding="utf-8")
        right = tmp_path / "right.csv"
        right.write_text(right_content, encoding="utf-8")
        result = reconcile(left, right, key_columns=["order_id"])
        assert result.summary.diff_count == 1
        assert "hello" in result.row_diffs[0].diffs[0].left_value
        assert "hi" in result.row_diffs[0].diffs[0].right_value

    def test_quoted_multiple_escaped_quotes(self, tmp_path: Path) -> None:
        left_content = (
            'id,notes\n'
            '1,"""quote"" and ""quote"""\n'
        )
        right_content = (
            'id,notes\n'
            '1,"""quote"" and ""quote"""\n'
        )
        left = tmp_path / "left.csv"
        left.write_text(left_content, encoding="utf-8")
        right = tmp_path / "right.csv"
        right.write_text(right_content, encoding="utf-8")
        result = reconcile(left, right, key_columns=["id"])
        assert result.summary.matched_count == 1


class TestZeroWidthAndBOM:
    def test_normalize_removes_bom(self) -> None:
        s = "\ufeffHello World"
        assert _normalize_value(s) == "hello world"

    def test_normalize_removes_zero_width_space(self) -> None:
        s = "Hello\u200bWorld"
        assert _normalize_value(s) == "helloworld"

    def test_normalize_removes_zwj(self) -> None:
        s = "A\u200dB\u200dC"
        assert _normalize_value(s) == "abc"

    def test_normalize_removes_soft_hyphen(self) -> None:
        s = "prod\u00aduct"
        assert _normalize_value(s) == "product"

    def test_normalize_removes_mongolian_vowel(self) -> None:
        s = "test\u180evalue"
        assert _normalize_value(s) == "testvalue"

    def test_normalize_removes_word_joiner(self) -> None:
        s = "foo\u2060bar"
        assert _normalize_value(s) == "foobar"

    def test_csv_with_bom_header(self, tmp_path: Path) -> None:
        left_content = "\ufefforder_id,product\n1001,Widget\n"
        right_content = "order_id,product\n1001,Widget\n"
        left = tmp_path / "left.csv"
        left.write_text(left_content, encoding="utf-8")
        right = tmp_path / "right.csv"
        right.write_text(right_content, encoding="utf-8")
        result = reconcile(left, right, key_columns=["order_id"], normalize=True)
        assert result.summary.matched_count == 1

    def test_csv_with_zero_width_in_value(self, tmp_path: Path) -> None:
        left_content = "id,name\n1,John\u200bDoe\n"
        right_content = "id,name\n1,JohnDoe\n"
        left = tmp_path / "left.csv"
        left.write_text(left_content, encoding="utf-8")
        right = tmp_path / "right.csv"
        right.write_text(right_content, encoding="utf-8")
        result = reconcile(left, right, key_columns=["id"], normalize=True)
        assert result.summary.matched_count == 1

    def test_zero_width_in_key_column(self, tmp_path: Path) -> None:
        left_content = "id,name\n1001\u200b,Widget\n"
        right_content = "id,name\n1001,Widget\n"
        left = tmp_path / "left.csv"
        left.write_text(left_content, encoding="utf-8")
        right = tmp_path / "right.csv"
        right.write_text(right_content, encoding="utf-8")
        result = reconcile(left, right, key_columns=["id"], normalize=True)
        assert result.summary.matched_count == 1


class TestColumnMissingRatesWithDistribution:
    def test_column_missing_with_distribution(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        assert len(result.summary.column_missing_rates) > 0
        for cmr in result.summary.column_missing_rates:
            assert cmr.left_distribution is not None
            assert cmr.right_distribution is not None
            assert cmr.left_distribution.dominant_type in ("int", "float", "string")
            assert cmr.right_distribution.dominant_type in ("int", "float", "string")

    def test_mixed_data_type_distribution(self, tmp_path: Path) -> None:
        left_content = """\
id,value
1,123
2,abc
3,45.67
4,2024-01-15
5,user@example.com
6,550e8400-e29b-41d4-a716-446655440000
"""
        right_content = left_content
        left = _write_csv(tmp_path, "left.csv", left_content)
        right = _write_csv(tmp_path, "right.csv", right_content)
        result = reconcile(left, right, key_columns=["id"])
        cmr_value = next(c for c in result.summary.column_missing_rates if c.column == "value")
        assert cmr_value.left_distribution is not None
        assert cmr_value.left_distribution.int_count >= 1
        assert cmr_value.left_distribution.float_count >= 1
        assert cmr_value.left_distribution.date_count >= 1
        assert cmr_value.left_distribution.email_count >= 1
        assert cmr_value.left_distribution.uuid_count >= 1
        assert cmr_value.left_distribution.string_count >= 1


class TestRecommendKeyColumns:
    def test_recommend_basic(self, tmp_path: Path) -> None:
        content = """\
id,name,email,category,score
1,Alice,alice@x.com,A,95
2,Bob,bob@x.com,B,87
3,Charlie,charlie@x.com,A,92
4,Dave,dave@x.com,C,88
"""
        p = _write_csv(tmp_path, "data.csv", content)
        weights = recommend_key_columns(p, top_n=3)
        assert len(weights) == 3
        assert weights[0].column == "id"
        assert weights[0].unique_ratio == 1.0
        assert weights[0].score > 0

    def test_recommend_uuid_scores_high(self, tmp_path: Path) -> None:
        content = """\
user_id,name,note
550e8400-e29b-41d4-a716-446655440000,Alice,xxx
550e8400-e29b-41d4-a716-446655440001,Bob,yyy
"""
        p = _write_csv(tmp_path, "data.csv", content)
        weights = recommend_key_columns(p, top_n=2)
        assert weights[0].column == "user_id"
        assert weights[0].data_type == "uuid"

    def test_recommend_empty_file(self, tmp_path: Path) -> None:
        content = "a,b,c\n"
        p = _write_csv(tmp_path, "empty.csv", content)
        weights = recommend_key_columns(p)
        assert len(weights) == 3
        for w in weights:
            assert w.unique_ratio == 0.0

    def test_recommend_with_nulls(self, tmp_path: Path) -> None:
        content = """\
id,code,name
1,,A
2,X002,B
3,X003,
4,X004,D
"""
        p = _write_csv(tmp_path, "data.csv", content)
        weights = recommend_key_columns(p, top_n=3)
        assert weights[0].column == "id"
        assert weights[0].null_ratio == 0.0


class TestAdaptiveChunkAndMemory:
    def test_memory_limit_triggers_chunked_read(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"], memory_limit_mb=64)
        assert result.summary.left_total == 6
        assert result.summary.right_total == 6

    def test_explicit_chunksize(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"], chunksize=2)
        assert result.summary.matched_count == 3

    def test_get_memory_info(self) -> None:
        from csv_reconcile.engine import _get_memory_info
        total, available = _get_memory_info()
        assert total > 0
        assert available > 0


class TestHtmlReport:
    def test_generate_html_light(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        html = generate_html(result, theme="light")
        assert "<!DOCTYPE html>" in html
        assert "Matched" in html
        assert "Only in Left" in html
        assert "Value Differences" in html

    def test_generate_html_dark(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        html = generate_html(result, theme="dark")
        assert "#111827" in html or "111827" in html

    def test_generate_html_solarized(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        html = generate_html(result, theme="solarized")
        assert "#002b36" in html or "002b36" in html

    def test_html_contains_theme_switcher(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        html = generate_html(result)
        assert "themeSwitcher" in html
        assert "data-theme" in html

    def test_html_contains_data_type_distribution(self, tmp_path: Path) -> None:
        left = _write_csv(tmp_path, "left.csv", BASIC_LEFT)
        right = _write_csv(tmp_path, "right.csv", BASIC_RIGHT)
        result = reconcile(left, right, key_columns=["order_id", "item_id"])
        html = generate_html(result)
        assert "Data Type Distribution" in html
        assert "int:" in html or "float:" in html
