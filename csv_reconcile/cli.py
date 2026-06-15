from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .engine import reconcile
from .report import print_report

app = typer.Typer(
    name="csv-reconcile",
    help="CSV 对账工具：关键字段匹配、差异定位、缺失行报告",
    add_completion=False,
)


@app.command()
def compare(
    left: Path = typer.Argument(..., help="左表 CSV 文件路径", exists=True),
    right: Path = typer.Argument(..., help="右表 CSV 文件路径", exists=True),
    keys: str = typer.Option(..., "--keys", "-k", help="关键字段，逗号分隔，如: order_id,item_id"),
    columns: Optional[str] = typer.Option(
        None, "--columns", "-c", help="比较字段，逗号分隔；默认比较除关键字段外的所有共有列"
    ),
    encoding: str = typer.Option("utf-8", "--encoding", "-e", help="CSV 文件编码"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="报告输出目录；不指定则仅控制台输出"),
) -> None:
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    if not key_list:
        typer.echo("错误: 至少指定一个关键字段", err=True)
        raise typer.Exit(code=1)

    col_list = None
    if columns is not None:
        col_list = [c.strip() for c in columns.split(",") if c.strip()]
        if not col_list:
            typer.echo("错误: --columns 不能为空", err=True)
            raise typer.Exit(code=1)

    try:
        result = reconcile(
            left_path=left,
            right_path=right,
            key_columns=key_list,
            compare_columns=col_list,
            encoding=encoding,
        )
    except ValueError as exc:
        typer.echo(f"错误: {exc}", err=True)
        raise typer.Exit(code=1)

    left_name = left.stem
    right_name = right.stem

    print_report(result, left_name, right_name, output_dir=output)


if __name__ == "__main__":
    app()
