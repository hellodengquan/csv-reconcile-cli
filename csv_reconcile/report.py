from __future__ import annotations

from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from .engine import ReconcileResult

console = Console()


def _fmt_key(key_values: dict[str, str]) -> str:
    return " | ".join(f"{k}={v}" for k, v in key_values.items())


def _fmt_pct(value: float) -> str:
    return f"{value:.2%}"


def print_summary(result: ReconcileResult, left_name: str, right_name: str) -> None:
    console.rule("[bold cyan]\u5bf9\u8d26\u6982\u89c8[/bold cyan]")
    s = result.summary

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("\u6307\u6807", style="cyan")
    table.add_column("\u503c", justify="right")

    table.add_row("\u5de6\u8868\u603b\u884c\u6570", str(s.left_total))
    table.add_row("\u53f3\u8868\u603b\u884c\u6570", str(s.right_total))
    table.add_row("\u884c\u6570\u5dee\u5f02", str(s.row_count_diff))
    table.add_row("\u5b8c\u5168\u5339\u914d\u884c\u6570", f"[green]{s.matched_count}[/green]")
    table.add_row("\u5b58\u5728\u5dee\u5f02\u884c\u6570", f"[yellow]{s.diff_count}[/yellow]")
    table.add_row("\u4ec5\u5de6\u8868\u5b58\u5728", f"[red]{s.left_only_count}[/red]")
    table.add_row("\u4ec5\u53f3\u8868\u5b58\u5728", f"[red]{s.right_only_count}[/red]")
    table.add_row("\u5de6\u8868\u7f3a\u5931\u7387", _fmt_pct(s.left_missing_rate))
    table.add_row("\u53f3\u8868\u7f3a\u5931\u7387", _fmt_pct(s.right_missing_rate))

    console.print(table)
    console.print()


def print_diffs(result: ReconcileResult, left_name: str, right_name: str) -> None:
    if not result.row_diffs:
        console.print("[green]\u6ca1\u6709\u5dee\u5f02\u884c.[/green]")
        return

    console.rule(f"[bold yellow]\u5dee\u5f02\u884c ({len(result.row_diffs)})[/bold yellow]")

    for idx, rd in enumerate(result.row_diffs, 1):
        table = Table(
            show_header=True,
            header_style="bold yellow",
            title=f"#{idx} {_fmt_key(rd.key_values)}",
        )
        table.add_column("\u5b57\u6bb5")
        table.add_column("\u5dee\u5f02\u7c7b\u578b")
        table.add_column(left_name, style="cyan")
        table.add_column(right_name, style="magenta")

        for d in rd.diffs:
            table.add_row(d.column, d.diff_type, d.left_value, d.right_value)

        console.print(table)
        console.print()


def print_missing(result: ReconcileResult, left_name: str, right_name: str) -> None:
    if result.left_only:
        console.rule(f"[bold red]\u4ec5\u5de6\u8868\u5b58\u5728\u7684\u884c ({result.summary.left_only_count})[/bold red]")
        df = pd.DataFrame(result.left_only)
        table = Table(show_header=True, header_style="bold red")
        for col in df.columns:
            table.add_column(col)
        for _, row in df.iterrows():
            table.add_row(*[str(v) for v in row])
        console.print(table)
        console.print()

    if result.right_only:
        console.rule(f"[bold red]\u4ec5\u53f3\u8868\u5b58\u5728\u7684\u884c ({result.summary.right_only_count})[/bold red]")
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
                row = {
                    **rd.key_values,
                    "\u5dee\u5f02\u5b57\u6bb5": d.column,
                    "\u5dee\u5f02\u7c7b\u578b": d.diff_type,
                    "\u5de6\u8868\u503c": d.left_value,
                    "\u53f3\u8868\u503c": d.right_value,
                }
                rows.append(row)
        df = pd.DataFrame(rows)
        df.to_csv(output_dir / "diffs.csv", index=False, encoding="utf-8-sig")

    s = result.summary
    summary_data = [
        ("\u5de6\u8868\u603b\u884c\u6570", str(s.left_total)),
        ("\u53f3\u8868\u603b\u884c\u6570", str(s.right_total)),
        ("\u884c\u6570\u5dee\u5f02", str(s.row_count_diff)),
        ("\u5b8c\u5168\u5339\u914d\u884c\u6570", str(s.matched_count)),
        ("\u5b58\u5728\u5dee\u5f02\u884c\u6570", str(s.diff_count)),
        ("\u4ec5\u5de6\u8868\u5b58\u5728", str(s.left_only_count)),
        ("\u4ec5\u53f3\u8868\u5b58\u5728", str(s.right_only_count)),
        ("\u5de6\u8868\u7f3a\u5931\u7387", _fmt_pct(s.left_missing_rate)),
        ("\u53f3\u8868\u7f3a\u5931\u7387", _fmt_pct(s.right_missing_rate)),
    ]
    df_summary = pd.DataFrame(summary_data, columns=["\u6307\u6807", "\u503c"])
    df_summary.to_csv(output_dir / "summary.csv", index=False, encoding="utf-8-sig")


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
        console.print(f"[bold green]\u62a5\u544a\u5df2\u5bfc\u51fa\u81f3: {output_dir}[/bold green]")
