from __future__ import annotations

from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from .engine import ReconcileResult


console = Console()


def _fmt_key(key_values: dict[str, str]) -> str:
    return " | ".join(f"{k}={v}" for k, v in key_values.items())


def print_summary(result: ReconcileResult, left_name: str, right_name: str) -> None:
    console.rule("[bold cyan]对账概览[/bold cyan]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("指标", style="cyan")
    table.add_column("值", justify="right")

    table.add_row("左表总行数", str(result.left_total))
    table.add_row("右表总行数", str(result.right_total))
    table.add_row("完全匹配行数", f"[green]{result.matched_count}[/green]")
    table.add_row("存在差异行数", f"[yellow]{len(result.row_diffs)}[/yellow]")
    table.add_row("仅左表存在", f"[red]{len(result.left_only)}[/red]")
    table.add_row("仅右表存在", f"[red]{len(result.right_only)}[/red]")

    console.print(table)
    console.print()


def print_diffs(result: ReconcileResult, left_name: str, right_name: str) -> None:
    if not result.row_diffs:
        console.print("[green]没有差异行。[/green]")
        return

    console.rule(f"[bold yellow]差异行 ({len(result.row_diffs)})[/bold yellow]")

    for idx, rd in enumerate(result.row_diffs, 1):
        table = Table(show_header=True, header_style="bold yellow", title=f"#{idx} {_fmt_key(rd.key_values)}")
        table.add_column("字段")
        table.add_column(left_name, style="cyan")
        table.add_column(right_name, style="magenta")

        for d in rd.diffs:
            table.add_row(d.column, d.left_value, d.right_value)

        console.print(table)
        console.print()


def print_missing(result: ReconcileResult, left_name: str, right_name: str) -> None:
    if result.left_only:
        console.rule(f"[bold red]仅左表存在的行 ({len(result.left_only)})[/bold red]")
        if result.left_only:
            df = pd.DataFrame(result.left_only)
            table = Table(show_header=True, header_style="bold red")
            for col in df.columns:
                table.add_column(col)
            for _, row in df.iterrows():
                table.add_row(*[str(v) for v in row])
            console.print(table)
            console.print()

    if result.right_only:
        console.rule(f"[bold red]仅右表存在的行 ({len(result.right_only)})[/bold red]")
        if result.right_only:
            df = pd.DataFrame(result.right_only)
            table = Table(show_header=True, header_style="bold red")
            for col in df.columns:
                table.add_column(col)
            for _, row in df.iterrows():
                table.add_row(*[str(v) for v in row])
            console.print(table)
            console.print()


def export_csv(result: ReconcileResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    if result.left_only:
        df = pd.DataFrame(result.left_only)
        df.to_csv(output_dir / "left_only.csv", index=False, encoding="utf-8-sig")

    if result.right_only:
        df = pd.DataFrame(result.right_only)
        df.to_csv(output_dir / "right_only.csv", index=False, encoding="utf-8-sig")

    if result.row_diffs:
        rows = []
        for rd in result.row_diffs:
            for d in rd.diffs:
                row = {**rd.key_values, "差异字段": d.column, "左表值": d.left_value, "右表值": d.right_value}
                rows.append(row)
        df = pd.DataFrame(rows)
        df.to_csv(output_dir / "diffs.csv", index=False, encoding="utf-8-sig")


def print_report(
    result: ReconcileResult,
    left_name: str,
    right_name: str,
    output_dir: Path | None = None,
) -> None:
    print_summary(result, left_name, right_name)
    print_diffs(result, left_name, right_name)
    print_missing(result, left_name, right_name)

    if output_dir is not None:
        export_csv(result, output_dir)
        console.print(f"[bold green]报告已导出至: {output_dir}[/bold green]")
