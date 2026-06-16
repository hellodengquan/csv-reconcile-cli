from __future__ import annotations

from pathlib import Path

import typer

from .engine import normalize_csv, reconcile
from .report import print_report

app = typer.Typer(
    name="csv-reconcile",
    help="CSV \u5bf9\u8d26\u5de5\u5177: \u6bd4\u5bf9\u3001\u5dee\u5f02\u5b9a\u4f4d\u3001\u7f3a\u5931\u884c\u62a5\u544a\u4e0e\u91cd\u6574",
    add_completion=False,
)


@app.command()
def compare(
    left: Path = typer.Argument(..., help="\u5de6\u8868 CSV \u6587\u4ef6\u8def\u5f84", exists=True),
    right: Path = typer.Argument(..., help="\u53f3\u8868 CSV \u6587\u4ef6\u8def\u5f84", exists=True),
    keys: str = typer.Option(..., "--keys", "-k", help="\u5173\u952e\u5b57\u6bb5, \u9017\u53f7\u5206\u9694, \u5982: order_id,item_id"),
    columns: str | None = typer.Option(
        None, "--columns", "-c", help="\u6bd4\u8f83\u5b57\u6bb5, \u9017\u53f7\u5206\u9694; \u9ed8\u8ba4\u6bd4\u8f83\u9664\u5173\u952e\u5b57\u6bb5\u5916\u7684\u6240\u6709\u5171\u6709\u5217"
    ),
    encoding: str = typer.Option(
        "utf-8",
        "--encoding",
        "-e",
        help="CSV \u6587\u4ef6\u7f16\u7801; \u4e24\u8868\u7f16\u7801\u4e0d\u540c\u65f6\u7528 | \u5206\u9694, \u5982 utf-8|gbk",
    ),
    normalize: bool = typer.Option(
        False,
        "--normalize",
        "-n",
        help="\u542f\u7528\u5f52\u4e00\u5316: \u5173\u952e\u5b57\u6bb5\u4e0e\u6bd4\u8f83\u5b57\u6bb5\u53bb\u9664\u9996\u5c3e\u7a7a\u767d\u5e76\u5ffd\u7565\u5927\u5c0f\u5199",
    ),
    memory_limit: int | None = typer.Option(
        None,
        "--memory-limit",
        "-m",
        help="\u5185\u5b58\u4e0a\u9650(MB), \u8d85\u8fc7\u540e\u81ea\u52a8\u5206\u5757\u8bfb\u53d6",
    ),
    chunksize: int | None = typer.Option(
        None,
        "--chunksize",
        help="\u5206\u5757\u8bfb\u53d6\u884c\u6570; \u8bbe\u7f6e\u540e\u6309\u6307\u5b9a\u884c\u6570\u5206\u5757",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="\u62a5\u544a\u8f93\u51fa\u76ee\u5f55; \u4e0d\u6307\u5b9a\u5219\u4ec5\u63a7\u5236\u53f0\u8f93\u51fa"
    ),
) -> None:
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    if not key_list:
        typer.echo("\u9519\u8bef: \u81f3\u5c11\u6307\u5b9a\u4e00\u4e2a\u5173\u952e\u5b57\u6bb5", err=True)
        raise typer.Exit(code=1)

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


if __name__ == "__main__":
    app()
