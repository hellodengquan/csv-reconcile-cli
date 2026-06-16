from __future__ import annotations

from pathlib import Path

from .engine import ReconcileResult


def _sql_escape(value: str) -> str:
    return value.replace("'", "''")


def _generate_update_statements(
    result: ReconcileResult,
    table_name: str,
    key_columns: list[str],
) -> list[str]:
    statements: list[str] = []
    for rd in result.row_diffs:
        for d in rd.diffs:
            where_parts = " AND ".join(
                f"{col} = '{_sql_escape(val)}'" for col, val in rd.key_values.items()
            )
            set_clause = f"{d.column} = '{_sql_escape(d.right_value)}'"
            sql = f"UPDATE {table_name} SET {set_clause} WHERE {where_parts};"
            statements.append(sql)
    return statements


def _generate_insert_statements(
    rows: list[dict[str, str]],
    table_name: str,
) -> list[str]:
    statements: list[str] = []
    if not rows:
        return statements
    columns = list(rows[0].keys())
    col_list = ", ".join(columns)
    for row in rows:
        val_list = ", ".join(f"'{_sql_escape(row[c])}'" for c in columns)
        sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({val_list});"
        statements.append(sql)
    return statements


def _generate_delete_statements(
    rows: list[dict[str, str]],
    table_name: str,
    key_columns: list[str],
    batch_size: int | None = None,
) -> list[str]:
    statements: list[str] = []
    if not rows:
        return statements

    if batch_size is None or len(key_columns) != 1:
        for row in rows:
            where_parts = " AND ".join(
                f"{col} = '{_sql_escape(row[col])}'" for col in key_columns if col in row
            )
            sql = f"DELETE FROM {table_name} WHERE {where_parts};"
            statements.append(sql)
    else:
        key_col = key_columns[0]
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            values = [f"'{_sql_escape(row[key_col])}'" for row in batch if key_col in row]
            if values:
                in_clause = ", ".join(values)
                sql = f"DELETE FROM {table_name} WHERE {key_col} IN ({in_clause});"
                statements.append(sql)

    return statements


def generate_fix_sql(
    result: ReconcileResult,
    table_name: str,
    key_columns: list[str],
    generate_inserts: bool = True,
    generate_deletes: bool = True,
    use_transaction: bool = True,
    delete_batch_size: int | None = None,
) -> str:
    parts: list[str] = []

    if use_transaction:
        parts.append("BEGIN TRANSACTION;")
        parts.append("")

    update_stmts = _generate_update_statements(result, table_name, key_columns)
    if update_stmts:
        parts.append("-- UPDATE: fix value mismatches")
        parts.extend(update_stmts)
        parts.append("")

    if generate_inserts and result.right_only:
        insert_stmts = _generate_insert_statements(result.right_only, table_name)
        if insert_stmts:
            parts.append("-- INSERT: add missing rows from right table")
            parts.extend(insert_stmts)
            parts.append("")

    if generate_deletes and result.left_only:
        delete_stmts = _generate_delete_statements(
            result.left_only, table_name, key_columns, delete_batch_size
        )
        if delete_stmts:
            batch_note = ""
            if delete_batch_size is not None and len(key_columns) == 1:
                batch_note = f" (batched {delete_batch_size})"
            parts.append(f"-- DELETE: remove rows only in left table{batch_note}")
            parts.extend(delete_stmts)
            parts.append("")

    if not parts or (len(parts) == 2 and parts[0] == "BEGIN TRANSACTION;"):
        parts.append("-- No differences found; no SQL to generate.")

    if use_transaction:
        parts.append("COMMIT;")

    return "\n".join(parts)


def export_fix_sql(
    result: ReconcileResult,
    output_path: Path,
    table_name: str,
    key_columns: list[str],
    generate_inserts: bool = True,
    generate_deletes: bool = True,
    use_transaction: bool = True,
    delete_batch_size: int | None = None,
) -> None:
    sql = generate_fix_sql(
        result,
        table_name,
        key_columns,
        generate_inserts,
        generate_deletes,
        use_transaction,
        delete_batch_size,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(sql, encoding="utf-8")
