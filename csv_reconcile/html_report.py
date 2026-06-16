from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import cast

from .engine import DiffCell, ReconcileResult, RowDiff

THEMES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#ffffff",
        "fg": "#1a1a1a",
        "muted": "#6b7280",
        "border": "#e5e7eb",
        "header_bg": "#f3f4f6",
        "diff_add_bg": "#dcfce7",
        "diff_add_fg": "#166534",
        "diff_del_bg": "#fee2e2",
        "diff_del_fg": "#991b1b",
        "success": "#059669",
        "warning": "#d97706",
        "danger": "#dc2626",
        "info": "#2563eb",
        "table_bg": "#fafafa",
        "row_alt_bg": "#f9fafb",
        "primary": "#2563eb",
        "primary_fg": "#ffffff",
    },
    "dark": {
        "bg": "#111827",
        "fg": "#f9fafb",
        "muted": "#9ca3af",
        "border": "#374151",
        "header_bg": "#1f2937",
        "diff_add_bg": "#052e16",
        "diff_add_fg": "#4ade80",
        "diff_del_bg": "#450a0a",
        "diff_del_fg": "#fca5a5",
        "success": "#34d399",
        "warning": "#fbbf24",
        "danger": "#f87171",
        "info": "#60a5fa",
        "table_bg": "#1f2937",
        "row_alt_bg": "#1e293b",
        "primary": "#3b82f6",
        "primary_fg": "#ffffff",
    },
    "solarized": {
        "bg": "#002b36",
        "fg": "#eee8d5",
        "muted": "#93a1a1",
        "border": "#073642",
        "header_bg": "#073642",
        "diff_add_bg": "#073642",
        "diff_add_fg": "#859900",
        "diff_del_bg": "#073642",
        "diff_del_fg": "#dc322f",
        "success": "#859900",
        "warning": "#b58900",
        "danger": "#dc322f",
        "info": "#268bd2",
        "table_bg": "#073642",
        "row_alt_bg": "#003541",
        "primary": "#268bd2",
        "primary_fg": "#fdf6e3",
    },
}


def _highlight_diff(left: str, right: str, theme: str) -> tuple[str, str]:
    sm = SequenceMatcher(None, left, right)
    left_html = ""
    right_html = ""
    styles = THEMES[theme]
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            left_html += left[i1:i2]
            right_html += right[j1:j2]
        elif tag == "replace":
            left_html += (
                f'<span style="background-color:{styles["diff_del_bg"]};'
                f'color:{styles["diff_del_fg"]};text-decoration:line-through;">'
                f'{left[i1:i2]}</span>'
            )
            right_html += (
                f'<span style="background-color:{styles["diff_add_bg"]};'
                f'color:{styles["diff_add_fg"]};font-weight:bold;">'
                f'{right[j1:j2]}</span>'
            )
        elif tag == "delete":
            left_html += (
                f'<span style="background-color:{styles["diff_del_bg"]};'
                f'color:{styles["diff_del_fg"]};text-decoration:line-through;">'
                f'{left[i1:i2]}</span>'
            )
        elif tag == "insert":
            right_html += (
                f'<span style="background-color:{styles["diff_add_bg"]};'
                f'color:{styles["diff_add_fg"]};font-weight:bold;">'
                f'{right[j1:j2]}</span>'
            )
    return left_html, right_html


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _color_for_rate(rate: float, styles: dict[str, str]) -> str:
    if rate == 0:
        return styles["success"]
    if rate < 0.05:
        return styles["warning"]
    return styles["danger"]


def generate_html(
    result: ReconcileResult,
    theme: str = "light",
    title: str = "CSV Reconciliation Report",
) -> str:
    styles = THEMES.get(theme, THEMES["light"])
    summary = result.summary

    overall_status = "clean"
    overall_status_color = styles["success"]
    if summary.diff_count > 0 or summary.left_only_count > 0 or summary.right_only_count > 0:
        overall_status = "differences"
        overall_status_color = styles["warning"]
    if summary.diff_count > 10 or max(summary.left_missing_rate, summary.right_missing_rate) > 0.1:
        overall_status = "critical"
        overall_status_color = styles["danger"]

    header = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{_escape_html(title)}</title>
<style>
    :root {{
        --bg: {styles['bg']};
        --fg: {styles['fg']};
        --muted: {styles['muted']};
        --border: {styles['border']};
        --header-bg: {styles['header_bg']};
        --success: {styles['success']};
        --warning: {styles['warning']};
        --danger: {styles['danger']};
        --info: {styles['info']};
        --primary: {styles['primary']};
        --primary-fg: {styles['primary_fg']};
        --row-alt: {styles['row_alt_bg']};
        --table-bg: {styles['table_bg']};
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
        background: var(--bg);
        color: var(--fg);
        padding: 24px;
        line-height: 1.6;
    }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    header {{ margin-bottom: 32px; }}
    h1 {{ font-size: 28px; margin-bottom: 8px; }}
    .status-badge {{
        display: inline-block;
        padding: 4px 16px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 14px;
        color: {styles['bg']};
        background: {overall_status_color};
        margin-bottom: 16px;
    }}
    .theme-switcher {{
        display: flex;
        gap: 8px;
        margin-bottom: 24px;
        flex-wrap: wrap;
    }}
    .theme-btn {{
        padding: 8px 16px;
        border: 1px solid var(--border);
        background: var(--table-bg);
        color: var(--fg);
        border-radius: 6px;
        cursor: pointer;
        font-size: 14px;
    }}
    .theme-btn.active {{
        background: var(--primary);
        color: var(--primary-fg);
        border-color: var(--primary);
    }}
    .theme-btn:hover {{ opacity: 0.9; }}
    .stats-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin-bottom: 32px;
    }}
    .stat-card {{
        background: var(--table-bg);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 16px;
    }}
    .stat-label {{ color: var(--muted); font-size: 13px; margin-bottom: 4px; }}
    .stat-value {{ font-size: 24px; font-weight: 700; }}
    .section {{
        background: var(--table-bg);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 24px;
    }}
    .section h2 {{
        font-size: 18px;
        margin-bottom: 16px;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--border);
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
    }}
    th, td {{
        text-align: left;
        padding: 10px 12px;
        border-bottom: 1px solid var(--border);
    }}
    th {{
        background: var(--header-bg);
        font-weight: 600;
        position: sticky;
        top: 0;
    }}
    tbody tr:nth-child(even) {{ background: var(--row-alt); }}
    tbody tr:hover {{ opacity: 0.95; }}
    .diff-table {{ table-layout: fixed; }}
    .diff-table td {{ overflow-wrap: break-word; word-wrap: break-word; }}
    .col-diff {{ width: 20%; }}
    .col-value {{ width: 40%; }}
    .muted {{ color: var(--muted); }}
    .empty {{ text-align: center; padding: 32px; color: var(--muted); }}
    footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--border); color: var(--muted); font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
    <header>
        <span class="status-badge">{overall_status.upper()}</span>
        <h1>{_escape_html(title)}</h1>
        <p class="muted">CSV Reconciliation Report</p>
    </header>
    <div class="theme-switcher" id="themeSwitcher">
        <button class="theme-btn {"active" if theme == "light" else ""}" data-theme="light">Light</button>
        <button class="theme-btn {"active" if theme == "dark" else ""}" data-theme="dark">Dark</button>
        <button class="theme-btn {"active" if theme == "solarized" else ""}" data-theme="solarized">Solarized</button>
    </div>
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-label">Total Rows (Left)</div>
            <div class="stat-value">{summary.left_total}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Total Rows (Right)</div>
            <div class="stat-value">{summary.right_total}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Row Count Diff</div>
            <div class="stat-value">{summary.row_count_diff}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Matched</div>
            <div class="stat-value" style="color: var(--success);">{summary.matched_count}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Value Diff</div>
            <div class="stat-value" style="color: var(--warning);">{summary.diff_count}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Only in Left</div>
            <div class="stat-value" style="color: var(--danger);">{summary.left_only_count}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Only in Right</div>
            <div class="stat-value" style="color: var(--danger);">{summary.right_only_count}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Left Missing Rate</div>
            <div class="stat-value" style="color: {_color_for_rate(summary.left_missing_rate, styles)};">{summary.left_missing_rate * 100:.2f}%</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Right Missing Rate</div>
            <div class="stat-value" style="color: {_color_for_rate(summary.right_missing_rate, styles)};">{summary.right_missing_rate * 100:.2f}%</div>
        </div>
    </div>
"""

    col_missing_html = ""
    if summary.column_missing_rates:
        col_missing_html = '<div class="section"><h2>Column Missing Rates &amp; Data Type Distribution</h2>'
        col_missing_html += '<table><thead><tr><th>Column</th><th>Left Missing</th><th>Right Missing</th><th>Left Type Distribution</th><th>Right Type Distribution</th></tr></thead><tbody>'
        for mr in summary.column_missing_rates:
            left_dist_parts = []
            if mr.left_distribution:
                d = mr.left_distribution
                total = max(1, d.total)
                for tname in ["int", "float", "date", "uuid", "email", "string"]:
                    cnt = getattr(d, f"{tname}_count")
                    if cnt > 0:
                        left_dist_parts.append(f"{tname}:{cnt / total * 100:.1f}%")
            right_dist_parts = []
            if mr.right_distribution:
                d = mr.right_distribution
                total = max(1, d.total)
                for tname in ["int", "float", "date", "uuid", "email", "string"]:
                    cnt = getattr(d, f"{tname}_count")
                    if cnt > 0:
                        right_dist_parts.append(f"{tname}:{cnt / total * 100:.1f}%")
            col_missing_html += (
                f"<tr>"
                f"<td><code>{_escape_html(mr.column)}</code></td>"
                f'<td style="color:{_color_for_rate(mr.left_missing_rate, styles)};">{mr.left_missing}/{mr.left_total} ({mr.left_missing_rate * 100:.2f}%)</td>'
                f'<td style="color:{_color_for_rate(mr.right_missing_rate, styles)};">{mr.right_missing}/{mr.right_total} ({mr.right_missing_rate * 100:.2f}%)</td>'
                f"<td>{', '.join(left_dist_parts) or '-'}</td>"
                f"<td>{', '.join(right_dist_parts) or '-'}</td>"
                f"</tr>"
            )
        col_missing_html += "</tbody></table></div>"

    diffs_html = ""
    if result.row_diffs:
        diffs_html = '<div class="section"><h2>Value Differences</h2>'
        diffs_html += f'<p class="muted" style="margin-bottom:12px;">Total {len(result.row_diffs)} rows with differences</p>'
        for rd in result.row_diffs:
            rd_casted = cast(RowDiff, rd)
            key_str = ", ".join(f"{k}={v}" for k, v in rd_casted.key_values.items())
            diffs_html += '<details open style="margin-bottom:16px;border:1px solid var(--border);border-radius:6px;overflow:hidden;">'
            diffs_html += f'<summary style="padding:12px;cursor:pointer;background:var(--header-bg);font-weight:600;">Row: {_escape_html(key_str)}</summary>'
            diffs_html += '<table class="diff-table" style="margin:0;"><thead><tr><th class="col-diff">Column</th><th class="col-value">Left</th><th class="col-value">Right</th></tr></thead><tbody>'
            diff_list = rd_casted.diffs
            for cell in diff_list:
                cell_casted = cast(DiffCell, cell)
                lv, rv = _highlight_diff(
                    _escape_html(cell_casted.left_value),
                    _escape_html(cell_casted.right_value),
                    theme,
                )
                diffs_html += (
                    f"<tr><td><code>{_escape_html(cell_casted.column)}</code></td>"
                    f"<td>{lv}</td><td>{rv}</td></tr>"
                )
            diffs_html += "</tbody></table></details>"
        diffs_html += "</div>"

    missing_html = ""
    if result.left_only or result.right_only:
        missing_html = '<div class="section"><h2>Missing Rows</h2>'
        if result.left_only:
            missing_html += f'<h3 style="margin-top:16px;color:var(--danger);">Only in Left ({len(result.left_only)} rows)</h3>'
            columns_left = list(result.left_only[0].keys())
            missing_html += '<table><thead><tr>'
            for c in columns_left:
                missing_html += f"<th>{_escape_html(c)}</th>"
            missing_html += "</tr></thead><tbody>"
            for row in result.left_only:
                missing_html += "<tr>"
                for c in columns_left:
                    missing_html += f"<td>{_escape_html(str(row[c]))}</td>"
                missing_html += "</tr>"
            missing_html += "</tbody></table>"
        if result.right_only:
            missing_html += f'<h3 style="margin-top:16px;color:var(--danger);">Only in Right ({len(result.right_only)} rows)</h3>'
            columns_right = list(result.right_only[0].keys())
            missing_html += '<table><thead><tr>'
            for c in columns_right:
                missing_html += f"<th>{_escape_html(c)}</th>"
            missing_html += "</tr></thead><tbody>"
            for row in result.right_only:
                missing_html += "<tr>"
                for c in columns_right:
                    missing_html += f"<td>{_escape_html(str(row[c]))}</td>"
                missing_html += "</tr>"
            missing_html += "</tbody></table>"
        missing_html += "</div>"

    switcher_js = """<script>
(function() {
    const themes = """ + str(THEMES).replace("'", '"') + """;
    const root = document.documentElement;
    const buttons = document.querySelectorAll('.theme-btn');

    function applyTheme(name) {
        const s = themes[name];
        root.style.setProperty('--bg', s.bg);
        root.style.setProperty('--fg', s.fg);
        root.style.setProperty('--muted', s.muted);
        root.style.setProperty('--border', s.border);
        root.style.setProperty('--header-bg', s.header_bg);
        root.style.setProperty('--success', s.success);
        root.style.setProperty('--warning', s.warning);
        root.style.setProperty('--danger', s.danger);
        root.style.setProperty('--info', s.info);
        root.style.setProperty('--primary', s.primary);
        root.style.setProperty('--primary-fg', s.primary_fg);
        root.style.setProperty('--row-alt', s.row_alt_bg);
        root.style.setProperty('--table-bg', s.table_bg);
        document.body.style.background = s.bg;
        document.body.style.color = s.fg;
        buttons.forEach(b => b.classList.toggle('active', b.dataset.theme === name));
        try { localStorage.setItem('csv-reconcile-theme', name); } catch(e) {}
    }

    buttons.forEach(btn => {
        btn.addEventListener('click', () => applyTheme(btn.dataset.theme));
    });

    try {
        const saved = localStorage.getItem('csv-reconcile-theme');
        if (saved && themes[saved]) applyTheme(saved);
    } catch(e) {}
})();
</script>"""

    footer = """<footer>Generated by csv-reconcile CLI</footer>
</div>
""" + switcher_js + """
</body>
</html>"""

    return header + col_missing_html + diffs_html + missing_html + footer


def export_html(
    result: ReconcileResult,
    output_path: Path,
    theme: str = "light",
    title: str = "CSV Reconciliation Report",
) -> None:
    html = generate_html(result, theme, title)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
