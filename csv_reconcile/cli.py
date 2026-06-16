from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .engine import normalize_csv, recommend_key_columns, reconcile
from .html_report import export_html
from .report import print_report
from .sql import export_fix_sql

app = typer.Typer(
    name="csv-reconcile",
    help="CSV \u5bf9\u8d26\u5de5\u5177: \u6bd4\u5bf9\u3001\u5dee\u5f02\u5b9a\u4f4d\u3001\u7f3a\u5931\u884c\u62a5\u544a\u4e0e\u91cd\u6574",
    add_completion=False,
)

console = Console()


@app.command()
def compare(
    left: Path = typer.Argument(..., help="\u5de6\u8868 CSV \u6587\u4ef6\u8def\u5f84", exists=True),
    right: Path = typer.Argument(..., help="\u53f3\u8868 CSV \u6587\u4ef6\u8def\u5f84", exists=True),
    keys: str = typer.Option(..., "--keys", "-k", help="\u4e3b\u5173\u952e\u5b57\u6bb5, \u9017\u53f7\u5206\u9694"),
    secondary: str = typer.Option(
        "", "--secondary", "-s", help="\u4ece\u5173\u952e\u5b57\u6bb5, \u9017\u53f7\u5206\u9694; \u4e3b\u4ece\u8054\u5408\u5339\u914d"
    ),
    columns: str | None = typer.Option(
        None, "--columns", "-c", help="\u6bd4\u8f83\u5b57\u6bb5, \u9017\u53f7\u5206\u9694; \u9ed8\u8ba4\u6bd4\u8f83\u9664\u5173\u952e\u5b57\u6bb5\u5916\u7684\u6240\u6709\u5171\u6709\u5217"
    ),
    encoding: str = typer.Option(
        "utf-8",
        "--encoding",
        "-e",
        help="CSV \u6587\u4ef6\u7f16\u7801; \u4e24\u8868\u7f16\u7801\u4e0d\u540c\u65f6\u7528 | \u5206\u9694",
    ),
    normalize: bool = typer.Option(
        False,
        "--normalize",
        "-n",
        help="\u542f\u7528\u5f52\u4e00\u5316: \u7a7a\u767d/\u5927\u5c0f\u5199/\u5168\u89d2\u534a\u89d2/NFC/\u96f6\u5bbd\u5b57\u7b26/BOM",
    ),
    memory_limit: int | None = typer.Option(
        None,
        "--memory-limit",
        "-m",
        help="\u5185\u5b58\u4e0a\u9650(MB), \u8d85\u8fc7\u540e\u81ea\u9002\u5e94\u5206\u5757\u8bfb\u53d6",
    ),
    chunksize: int | None = typer.Option(
        None,
        "--chunksize",
        help="\u5206\u5757\u8bfb\u53d6\u884c\u6570; \u8bbe\u7f6e\u540e\u6309\u6307\u5b9a\u884c\u6570\u5206\u5757",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="\u62a5\u544a\u8f93\u51fa\u76ee\u5f55; \u4e0d\u6307\u5b9a\u5219\u4ec5\u63a7\u5236\u53f0\u8f93\u51fa"
    ),
    html: Path | None = typer.Option(
        None, "--html", help="HTML \u62a5\u544a\u8f93\u51fa\u8def\u5f84"
    ),
    theme: str = typer.Option(
        "light",
        "--theme",
        help="HTML \u4e3b\u9898: light/dark/solarized",
    ),
) -> None:
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    if not key_list:
        typer.echo("\u9519\u8bef: \u81f3\u5c11\u6307\u5b9a\u4e00\u4e2a\u4e3b\u5173\u952e\u5b57\u6bb5", err=True)
        raise typer.Exit(code=1)

    if theme not in ("light", "dark", "solarized", "high-contrast"):
        typer.echo(f"\u9519\u8bef: \u4e3b\u9898\u5fc5\u987b\u662f light/dark/solarized/high-contrast \u4e4b\u4e00: {theme}", err=True)
        raise typer.Exit(code=1)

    secondary_list: list[str] | None = None
    if secondary:
        secondary_list = [s.strip() for s in secondary.split(",") if s.strip()]

    col_list: list[str] | None = None
    if columns is not None:
        col_list = [c.strip() for c in columns.split(",") if c.strip()]
        if not col_list:
            typer.echo("\u9519\u8bef: --columns \u4e0d\u80fd\u4e3a\u7a7a", err=True)
            raise typer.Exit(code=1)

    try:
        result = reconcile(
            left_path=left,
            right_path=right,
            key_columns=key_list,
            compare_columns=col_list,
            secondary_keys=secondary_list,
            encoding=encoding,
            normalize=normalize,
            chunksize=chunksize,
            memory_limit_mb=memory_limit,
        )
    except ValueError as exc:
        typer.echo(f"\u9519\u8bef: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    left_name = left.stem
    right_name = right.stem

    print_report(result, left_name, right_name, output_dir=output)

    if html is not None:
        export_html(result, html, theme=theme, title=f"{left_name} vs {right_name}")
        typer.echo(f"HTML \u62a5\u544a\u5df2\u5bfc\u51fa\u81f3: {html}")


@app.command(name="suggest-keys")
def suggest_keys(
    path: Path = typer.Argument(..., help="CSV \u6587\u4ef6\u8def\u5f84", exists=True),
    encoding: str = typer.Option("utf-8", "--encoding", "-e", help="CSV \u6587\u4ef6\u7f16\u7801"),
    top_n: int = typer.Option(5, "--top-n", "-n", help="\u63a8\u8350\u5217\u6570"),
    primary_only: int = typer.Option(1, "--primary-only", "-p", help="\u63a8\u8350\u524d N \u5217\u4f5c\u4e3a\u4e3b\u952e\u7ec4\u5408"),
) -> None:
    try:
        weights = recommend_key_columns(path, encoding, top_n=max(top_n, primary_only))
    except Exception as exc:
        typer.echo(f"\u9519\u8bef: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if not weights:
        typer.echo("\u65e0\u6cd5\u63a8\u8350\u5173\u952e\u5217\uff08\u6587\u4ef6\u4e3a\u7a7a\uff09")
        return

    typer.echo(f"\ud83c\udfaf \u6309\u5217\u6743\u91cd\u63a8\u8350\u7684\u5173\u952e\u5b57\u6bb5: {path}")
    typer.echo("")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Rank", style="cyan")
    table.add_column("Column", style="bold")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Unique%", justify="right")
    table.add_column("Null%", justify="right")
    table.add_column("AvgLen", justify="right")
    table.add_column("Type", style="magenta")

    has_uniform = any(w.is_uniform_fallback for w in weights)
    if has_uniform:
        typer.echo(
            "\u26a0\ufe0f  \u6837\u672c\u884c\u6570\u8f83\u5c11 (< 30), \u6743\u91cd\u63a8\u8350\u5df2\u9000\u56de\u5747\u5300\u5206\u914d\u3002"
            "\u5efa\u8bae\u63d0\u4f9b\u66f4\u591a\u6570\u636e\u6216\u624b\u52a8\u6307\u5b9a\u5173\u952e\u5217\u3002"
        )
        typer.echo("")

    for i, w in enumerate(weights, 1):
        rank = f"{i:>2}"
        if w.is_uniform_fallback:
            rank += " \u2696\ufe0f"
        elif i <= primary_only:
            rank += " \u2b50"
        table.add_row(
            rank,
            w.column,
            f"{w.score:.4f}",
            f"{w.unique_ratio * 100:.1f}%",
            f"{w.null_ratio * 100:.1f}%",
            f"{w.avg_length:.1f}",
            w.data_type,
        )

    console.print(table)
    typer.echo("")

    if has_uniform:
        typer.echo(
            "\ud83d\udca1 \u5747\u5300\u6743\u91cd\u4e0b\u6309\u539f\u59cb\u5217\u987a\u5e8f\u63a8\u8350, "
            "\u8bf7\u6839\u636e\u4e1a\u52a1\u77e5\u8bc6\u8c03\u6574\u5173\u952e\u5217\u9009\u62e9\u3002"
        )
        typer.echo("")

    primary = [w.column for w in weights[:primary_only]]
    secondary = [w.column for w in weights[primary_only:]]

    typer.echo(f"\ud83d\udca1 \u4e3b\u952e\u63a8\u8350: --keys {','.join(primary)}")
    if secondary:
        typer.echo(f"\ud83d\udca1 \u4ece\u952e\u63a8\u8350: --secondary {','.join(secondary)}")


@app.command()
def normalize(
    input: Path = typer.Argument(..., help="\u8f93\u5165 CSV \u6587\u4ef6\u8def\u5f84", exists=True),
    output: Path = typer.Argument(..., help="\u8f93\u51fa CSV \u6587\u4ef6\u8def\u5f84"),
    encoding: str = typer.Option("utf-8", "--encoding", "-e", help="\u8f93\u5165\u6587\u4ef6\u7f16\u7801"),
) -> None:
    try:
        normalize_csv(input, output, encoding)
    except ValueError as exc:
        typer.echo(f"\u9519\u8bef: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"\u5df2\u5f52\u4e00\u5316\u8f93\u51fa\u81f3: {output}")


@app.command(name="fix-sql")
def fix_sql(
    left: Path = typer.Argument(..., help="\u5de6\u8868 CSV \u6587\u4ef6\u8def\u5f84", exists=True),
    right: Path = typer.Argument(..., help="\u53f3\u8868 CSV \u6587\u4ef6\u8def\u5f84", exists=True),
    keys: str = typer.Option(..., "--keys", "-k", help="\u4e3b\u5173\u952e\u5b57\u6bb5, \u9017\u53f7\u5206\u9694"),
    secondary: str = typer.Option(
        "", "--secondary", "-s", help="\u4ece\u5173\u952e\u5b57\u6bb5, \u9017\u53f7\u5206\u9694"
    ),
    columns: str | None = typer.Option(
        None, "--columns", "-c", help="\u6bd4\u8f83\u5b57\u6bb5, \u9017\u53f7\u5206\u9694"
    ),
    table: str = typer.Option(
        "target_table", "--table", "-t", help="\u76ee\u6807 SQL \u8868\u540d"
    ),
    encoding: str = typer.Option("utf-8", "--encoding", "-e", help="CSV \u6587\u4ef6\u7f16\u7801"),
    normalize: bool = typer.Option(False, "--normalize", "-n", help="\u542f\u7528\u5f52\u4e00\u5316"),
    memory_limit: int | None = typer.Option(None, "--memory-limit", "-m", help="\u5185\u5b58\u4e0a\u9650(MB)"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="SQL \u8f93\u51fa\u6587\u4ef6\u8def\u5f84; \u4e0d\u6307\u5b9a\u5219\u8f93\u51fa\u5230\u63a7\u5236\u53f0"
    ),
    no_insert: bool = typer.Option(False, "--no-insert", help="\u4e0d\u751f\u6210 INSERT \u8bed\u53e5"),
    no_delete: bool = typer.Option(False, "--no-delete", help="\u4e0d\u751f\u6210 DELETE \u8bed\u53e5"),
    no_transaction: bool = typer.Option(False, "--no-transaction", help="\u4e0d\u751f\u6210 BEGIN/COMMIT \u4e8b\u52a1\u8fb9\u754c"),
    delete_batch_size: int | None = typer.Option(
        None,
        "--delete-batch-size",
        help="DELETE \u6279\u6b21\u5927\u5c0f(\u4ec5\u5355\u5217\u4e3b\u952e\u6709\u6548); \u4e0d\u8bbe\u7f6e\u5219\u6bcf\u884c\u4e00\u6761 DELETE",
    ),
) -> None:
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    if not key_list:
        typer.echo("\u9519\u8bef: \u81f3\u5c11\u6307\u5b9a\u4e00\u4e2a\u4e3b\u5173\u952e\u5b57\u6bb5", err=True)
        raise typer.Exit(code=1)

    secondary_list: list[str] | None = None
    if secondary:
        secondary_list = [s.strip() for s in secondary.split(",") if s.strip()]

    col_list: list[str] | None = None
    if columns is not None:
        col_list = [c.strip() for c in columns.split(",") if c.strip()]

    try:
        result = reconcile(
            left_path=left,
            right_path=right,
            key_columns=key_list,
            compare_columns=col_list,
            secondary_keys=secondary_list,
            encoding=encoding,
            normalize=normalize,
            memory_limit_mb=memory_limit,
        )
    except ValueError as exc:
        typer.echo(f"\u9519\u8bef: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    from .sql import generate_fix_sql

    sql = generate_fix_sql(
        result,
        table_name=table,
        key_columns=key_list,
        generate_inserts=not no_insert,
        generate_deletes=not no_delete,
        use_transaction=not no_transaction,
        delete_batch_size=delete_batch_size,
    )

    if output is not None:
        export_fix_sql(
            result,
            output,
            table_name=table,
            key_columns=key_list,
            generate_inserts=not no_insert,
            generate_deletes=not no_delete,
            use_transaction=not no_transaction,
            delete_batch_size=delete_batch_size,
        )
        typer.echo(f"\u4fee\u590d SQL \u5df2\u5bfc\u51fa\u81f3: {output}")
    else:
        typer.echo(sql)


if __name__ == "__main__":
    app()
