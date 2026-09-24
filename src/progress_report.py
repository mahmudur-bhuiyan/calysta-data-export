"""Facility progress HTML report — done/pending + per-folder audit table + charts."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from export_status import (
    ALL_CATEGORIES,
    CATEGORY_SHORT,
    patient_progress_row,
)


def build_progress_rows(
    patient_data: List[Dict[str, str]],
    base_downloads_path: str,
    to_pascalcase,
) -> List[Dict[str, Any]]:
    rows = []
    for p in patient_data:
        pid = p["id"]
        first = to_pascalcase(p["first_name"])
        last = to_pascalcase(p["last_name"])
        full_name = f"{first} {last}"
        folder = os.path.join(base_downloads_path, f"{pid}_{first}_{last}")
        rows.append(patient_progress_row(pid, full_name, folder))
    return rows


def summarize_progress(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {
        "total": len(rows),
        "complete": 0,
        "partial": 0,
        "pending": 0,
        "failed": 0,
    }
    for r in rows:
        s = (r.get("status") or "").lower()
        if s == "complete":
            summary["complete"] += 1
        elif s == "partial":
            summary["partial"] += 1
        elif s == "failed":
            summary["failed"] += 1
        else:
            summary["pending"] += 1
    return summary


def generate_progress_report(
    facility_name: str,
    patient_data: List[Dict[str, str]],
    base_downloads_path: str,
    output_dir: str,
    to_pascalcase,
    custom_filename: str = None,
) -> str:
    """
    Scan downloads for every patient in the CSV and write a shareable HTML report.
    Returns path to the HTML file.
    """
    rows = build_progress_rows(patient_data, base_downloads_path, to_pascalcase)
    summary = summarize_progress(rows)
    total = summary["total"] or 1
    pct = round(100.0 * summary["complete"] / total, 1)

    os.makedirs(output_dir, exist_ok=True)
    if not custom_filename:
        safe = "".join(c if c.isalnum() or c in " _-" else "" for c in facility_name).strip()
        safe = safe.replace(" ", "_") or "Facility"
        custom_filename = f"{safe}_Export_Progress_{datetime.now().strftime('%m-%d-%Y')}.html"

    out_path = os.path.join(output_dir, custom_filename)

    # Category completion counts for bar chart
    cat_done = []
    cat_labels = []
    for cat in ALL_CATEGORIES:
        cat_labels.append(CATEGORY_SHORT[cat])
        done_n = 0
        for r in rows:
            st = (r["categories"].get(cat) or {}).get("state")
            if st in ("done", "done_empty"):
                done_n += 1
        cat_done.append(done_n)

    table_rows_html = []
    for r in rows:
        status = r["status"]
        badge_class = {
            "Complete": "badge-ok",
            "Partial": "badge-warn",
            "Failed": "badge-fail",
            "Pending": "badge-pending",
        }.get(status, "badge-pending")

        cells = []
        for cat in ALL_CATEGORIES:
            info = r["categories"].get(cat) or {}
            label = info.get("label") or "pending"
            st = info.get("state") or "pending"
            cell_class = {
                "done": "cell-ok",
                "done_empty": "cell-empty",
                "partial": "cell-partial",
                "failed": "cell-fail",
                "pending": "cell-pending",
            }.get(st, "cell-pending")
            cells.append(f'<td class="{cell_class}">{_esc(label)}</td>')

        table_rows_html.append(
            f"""<tr data-status="{_esc(status.lower())}">
            <td>{_esc(r['patient_id'])}</td>
            <td>{_esc(r['patient_name'])}</td>
            <td><span class="badge {badge_class}">{_esc(status)}</span></td>
            <td class="center">{r['done_categories']}/{r['total_categories']}</td>
            {''.join(cells)}
            </tr>"""
        )

    header_cats = "".join(
        f"<th title=\"{_esc(cat)}\">{_esc(CATEGORY_SHORT[cat])}</th>"
        for cat in ALL_CATEGORIES
    )

    chart_status = json.dumps([
        summary["complete"],
        summary["partial"],
        summary["pending"],
        summary["failed"],
    ])
    chart_cat_labels = json.dumps(cat_labels)
    chart_cat_done = json.dumps(cat_done)
    chart_cat_total = json.dumps([summary["total"]] * len(ALL_CATEGORIES))

    generated = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(facility_name)} — Export Progress</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg: #f4f7fb;
      --card: #ffffff;
      --ink: #1a2332;
      --muted: #5b6b7c;
      --ok: #1b7f4e;
      --ok-bg: #e6f6ee;
      --warn: #b45309;
      --warn-bg: #fff7ed;
      --fail: #b91c1c;
      --fail-bg: #fef2f2;
      --pending: #64748b;
      --pending-bg: #f1f5f9;
      --line: #e2e8f0;
      --accent: #0f4c81;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      background: linear-gradient(180deg, #e8eef5 0%, var(--bg) 40%);
      color: var(--ink);
      line-height: 1.45;
    }}
    .wrap {{ max-width: 1400px; margin: 0 auto; padding: 28px 20px 60px; }}
    header {{
      background: var(--card);
      border-radius: 16px;
      padding: 28px 32px;
      box-shadow: 0 8px 30px rgba(15, 76, 129, 0.08);
      border: 1px solid var(--line);
      margin-bottom: 22px;
    }}
    header h1 {{ margin: 0 0 8px; font-size: 1.75rem; color: var(--accent); }}
    header p {{ margin: 4px 0; color: var(--muted); }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 14px;
      margin-bottom: 22px;
    }}
    .kpi {{
      background: var(--card);
      border-radius: 14px;
      padding: 18px 16px;
      border: 1px solid var(--line);
      box-shadow: 0 4px 16px rgba(0,0,0,0.04);
    }}
    .kpi .label {{ font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }}
    .kpi .value {{ font-size: 1.9rem; font-weight: 700; margin-top: 6px; }}
    .kpi.ok .value {{ color: var(--ok); }}
    .kpi.warn .value {{ color: var(--warn); }}
    .kpi.fail .value {{ color: var(--fail); }}
    .kpi.pending .value {{ color: var(--pending); }}
    .progress-block {{
      background: var(--card);
      border-radius: 14px;
      padding: 18px 20px;
      border: 1px solid var(--line);
      margin-bottom: 22px;
    }}
    .bar-track {{
      height: 18px;
      background: var(--pending-bg);
      border-radius: 999px;
      overflow: hidden;
      margin-top: 10px;
    }}
    .bar-fill {{
      height: 100%;
      width: {pct}%;
      background: linear-gradient(90deg, #0f4c81, #1b7f4e);
      border-radius: 999px;
      transition: width 0.4s ease;
    }}
    .charts {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
      margin-bottom: 22px;
    }}
    .chart-card {{
      background: var(--card);
      border-radius: 14px;
      padding: 18px;
      border: 1px solid var(--line);
      min-height: 320px;
    }}
    .chart-card h2 {{ margin: 0 0 12px; font-size: 1.05rem; }}
    .toolbar {{
      display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
      margin-bottom: 12px;
    }}
    .toolbar button {{
      border: 1px solid var(--line);
      background: var(--card);
      border-radius: 999px;
      padding: 6px 14px;
      cursor: pointer;
      font-size: 0.85rem;
    }}
    .toolbar button.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    .table-card {{
      background: var(--card);
      border-radius: 14px;
      border: 1px solid var(--line);
      overflow: auto;
      box-shadow: 0 4px 16px rgba(0,0,0,0.04);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
      min-width: 1100px;
    }}
    th, td {{
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      white-space: nowrap;
    }}
    th {{
      position: sticky; top: 0;
      background: #0f4c81;
      color: #fff;
      font-weight: 600;
      z-index: 1;
    }}
    tr:hover td {{ background: #f8fafc; }}
    .center {{ text-align: center; }}
    .badge {{
      display: inline-block;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 600;
    }}
    .badge-ok {{ background: var(--ok-bg); color: var(--ok); }}
    .badge-warn {{ background: var(--warn-bg); color: var(--warn); }}
    .badge-fail {{ background: var(--fail-bg); color: var(--fail); }}
    .badge-pending {{ background: var(--pending-bg); color: var(--pending); }}
    .cell-ok {{ color: var(--ok); font-weight: 600; }}
    .cell-empty {{ color: var(--pending); }}
    .cell-partial {{ color: var(--warn); font-weight: 600; }}
    .cell-fail {{ color: var(--fail); font-weight: 600; }}
    .cell-pending {{ color: #94a3b8; }}
    footer {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 0.85rem;
      text-align: center;
    }}
    .legend {{
      display: flex; flex-wrap: wrap; gap: 12px;
      font-size: 0.8rem; color: var(--muted); margin: 8px 0 0;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>{_esc(facility_name)} — Export Progress</h1>
      <p>Patient document export status across all 10 data categories.</p>
      <p>Generated: {generated}</p>
    </header>

    <div class="kpis">
      <div class="kpi"><div class="label">Total patients</div><div class="value">{summary['total']}</div></div>
      <div class="kpi ok"><div class="label">Complete</div><div class="value">{summary['complete']}</div></div>
      <div class="kpi warn"><div class="label">Partial</div><div class="value">{summary['partial']}</div></div>
      <div class="kpi pending"><div class="label">Pending</div><div class="value">{summary['pending']}</div></div>
      <div class="kpi fail"><div class="label">Failed</div><div class="value">{summary['failed']}</div></div>
      <div class="kpi"><div class="label">% Complete</div><div class="value">{pct}%</div></div>
    </div>

    <div class="progress-block">
      <strong>Overall completion</strong>
      <span style="float:right;color:var(--muted)">{summary['complete']} of {summary['total']} patients</span>
      <div class="bar-track"><div class="bar-fill"></div></div>
      <div class="legend">
        <span><strong>empty ok</strong> = category checked, no records on portal</span>
        <span><strong>5 pdf / 10 jpg</strong> = files downloaded</span>
        <span><strong>partial</strong> = files present but category not finished</span>
        <span><strong>pending</strong> = not started or incomplete</span>
      </div>
    </div>

    <div class="charts">
      <div class="chart-card">
        <h2>Patient status</h2>
        <canvas id="statusChart" height="220"></canvas>
      </div>
      <div class="chart-card">
        <h2>Category completion (patients done)</h2>
        <canvas id="categoryChart" height="220"></canvas>
      </div>
    </div>

    <div class="toolbar">
      <strong>Filter:</strong>
      <button type="button" class="active" data-filter="all">All</button>
      <button type="button" data-filter="complete">Complete</button>
      <button type="button" data-filter="partial">Partial</button>
      <button type="button" data-filter="pending">Pending</button>
      <button type="button" data-filter="failed">Failed</button>
    </div>

    <div class="table-card">
      <table id="progressTable">
        <thead>
          <tr>
            <th>Patient ID</th>
            <th>Full name</th>
            <th>Status</th>
            <th>Done</th>
            {header_cats}
          </tr>
        </thead>
        <tbody>
          {''.join(table_rows_html)}
        </tbody>
      </table>
    </div>

    <footer>
      Calysta Pro Facility Data Export — share this file with the facility owner as a progress snapshot.
    </footer>
  </div>

  <script>
    const statusData = {chart_status};
    const catLabels = {chart_cat_labels};
    const catDone = {chart_cat_done};
    const catTotal = {chart_cat_total};

    new Chart(document.getElementById('statusChart'), {{
      type: 'doughnut',
      data: {{
        labels: ['Complete', 'Partial', 'Pending', 'Failed'],
        datasets: [{{
          data: statusData,
          backgroundColor: ['#1b7f4e', '#b45309', '#94a3b8', '#b91c1c'],
          borderWidth: 0
        }}]
      }},
      options: {{
        plugins: {{ legend: {{ position: 'bottom' }} }},
        cutout: '58%'
      }}
    }});

    new Chart(document.getElementById('categoryChart'), {{
      type: 'bar',
      data: {{
        labels: catLabels,
        datasets: [
          {{
            label: 'Done',
            data: catDone,
            backgroundColor: '#0f4c81'
          }},
          {{
            label: 'Remaining',
            data: catTotal.map((t, i) => Math.max(0, t - catDone[i])),
            backgroundColor: '#e2e8f0'
          }}
        ]
      }},
      options: {{
        responsive: true,
        scales: {{
          x: {{ stacked: true }},
          y: {{ stacked: true, beginAtZero: true, ticks: {{ precision: 0 }} }}
        }},
        plugins: {{ legend: {{ position: 'bottom' }} }}
      }}
    }});

    document.querySelectorAll('.toolbar button').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.toolbar button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const f = btn.dataset.filter;
        document.querySelectorAll('#progressTable tbody tr').forEach(tr => {{
          const st = tr.dataset.status;
          tr.style.display = (f === 'all' || st === f) ? '' : 'none';
        }});
      }});
    }});
  </script>
</body>
</html>
"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def _esc(value: Any) -> str:
    s = "" if value is None else str(value)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
