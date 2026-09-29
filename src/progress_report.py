"""Facility delivery HTML report — file counts and per-patient breakdown."""

from __future__ import annotations

import csv
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

from export_index import resolve_patient_folder
from export_status import (
    ALL_CATEGORIES,
    CATEGORY_APPOINTMENTS,
    CATEGORY_CONSENTS,
    CATEGORY_CREDITS,
    CATEGORY_DETAILS,
    CATEGORY_ENCOUNTERS,
    CATEGORY_IMAGES,
    CATEGORY_INVOICES,
    CATEGORY_MEMBERSHIP,
    CATEGORY_SERVICES,
    CATEGORY_SMS,
    folder_file_summary,
    patient_progress_row,
)

DELIVERY_CATEGORY_META = [
    (CATEGORY_DETAILS, "Patient Details", "CSV"),
    (CATEGORY_IMAGES, "Images", "JPG"),
    (CATEGORY_APPOINTMENTS, "Appointments", "CSV"),
    (CATEGORY_SERVICES, "Services", "CSV"),
    (CATEGORY_ENCOUNTERS, "Encounters", "PDF"),
    (CATEGORY_CONSENTS, "Consents", "PDF"),
    (CATEGORY_INVOICES, "Invoices", "PDF"),
    (CATEGORY_MEMBERSHIP, "Membership Invoices", "PDF"),
    (CATEGORY_CREDITS, "Available Credits", "CSV"),
    (CATEGORY_SMS, "SMS Log", "CSV"),
]


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
        folder = resolve_patient_folder(base_downloads_path, p, to_pascalcase)
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


def delivery_report_filename(facility_name: str, when: datetime | None = None) -> str:
    when = when or datetime.now()
    safe = "".join(c if c.isalnum() or c in " _-" else "" for c in facility_name).strip()
    safe = re.sub(r"[\s_]+", "_", safe) or "Facility"
    return f"{safe}_Delivery_Report_{when.strftime('%m-%d-%Y')}.html"


def _sort_key_patient_id(patient_id: str) -> tuple:
    pid = str(patient_id).strip()
    if pid.isdigit():
        return (0, int(pid))
    return (1, pid)


def _category_file_counts(patient_folder: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for cat in ALL_CATEGORIES:
        sub = os.path.join(patient_folder, cat)
        if os.path.isdir(sub):
            count, _ = folder_file_summary(sub)
            counts[cat] = count
        else:
            counts[cat] = 0
    return counts


def _read_patient_contact(patient_folder: str) -> Tuple[str, str]:
    details_dir = os.path.join(patient_folder, CATEGORY_DETAILS)
    if not os.path.isdir(details_dir):
        return "", ""
    for name in sorted(os.listdir(details_dir)):
        if not name.endswith("_details.csv"):
            continue
        path = os.path.join(details_dir, name)
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                row = next(csv.DictReader(f), None)
            if not row:
                continue
            email = (row.get("Email") or row.get("email") or "").strip()
            phone = (
                row.get("Cell phone")
                or row.get("Cell Phone")
                or row.get("work_phone")
                or row.get("home_phone")
                or ""
            ).strip()
            return phone, email
        except OSError:
            continue
    return "", ""


def _digits_only(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def _build_delivery_rows(
    patient_data: List[Dict[str, str]],
    base_downloads_path: str,
    to_pascalcase,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for patient in patient_data:
        pid = str(patient["id"]).strip()
        first = to_pascalcase(patient["first_name"])
        last = to_pascalcase(patient["last_name"])
        full_name = f"{first} {last}"
        folder = resolve_patient_folder(base_downloads_path, patient, to_pascalcase)
        counts = _category_file_counts(folder)
        phone, email = _read_patient_contact(folder)
        total_files = sum(counts.values())
        rows.append(
            {
                "patient_id": pid,
                "patient_name": full_name,
                "phone": phone,
                "email": email,
                "total_files": total_files,
                "counts": counts,
                "search": " ".join(
                    filter(
                        None,
                        [
                            pid,
                            full_name.lower(),
                            email.lower(),
                            phone.lower(),
                            _digits_only(phone),
                        ],
                    )
                ),
            }
        )
    rows.sort(key=lambda r: _sort_key_patient_id(r["patient_id"]), reverse=True)
    return rows


def _summarize_category_totals(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    totals = {cat: 0 for cat in ALL_CATEGORIES}
    for row in rows:
        for cat in ALL_CATEGORIES:
            totals[cat] += int((row.get("counts") or {}).get(cat) or 0)
    return totals


def _render_volume_cards(category_totals: Dict[str, int]) -> str:
    max_count = max(category_totals.values()) if category_totals else 0
    max_count = max_count or 1
    cards = []
    for cat, label, _fmt in DELIVERY_CATEGORY_META:
        count = category_totals.get(cat, 0)
        width = round(100.0 * count / max_count, 2)
        cards.append(
            f"""        <div class="vol-card">
          <div class="vol-top">
            <div class="vol-label">{_esc(label)}</div>
            <div class="vol-value">{count:,}</div>
          </div>
          <div class="vol-track" aria-hidden="true">
            <div class="vol-fill" style="width:{width}%"></div>
          </div>
          <div class="vol-unit">Files</div>
        </div>"""
        )
    return "\n".join(cards)


def _render_table_header() -> str:
    headers = [
        "<th>Patient ID</th>",
        "<th>Name</th>",
        "<th>Cell Phone</th>",
        "<th>Email</th>",
        '<th class="num">Total Files</th>',
    ]
    for _cat, label, fmt in DELIVERY_CATEGORY_META:
        headers.append(
            f'<th class="num cat-h" title="{_esc(label)} ({fmt})">'
            f'<span class="h-main">{_esc(label)}</span>'
            f'<span class="h-fmt">({fmt})</span></th>'
        )
    return "".join(headers)


def _render_count_cell(count: int) -> str:
    css = "num zero" if count == 0 else "num"
    return f'<td class="{css}">{count}</td>'


def _render_table_rows(rows: List[Dict[str, Any]]) -> str:
    parts = []
    for row in rows:
        counts = row["counts"]
        cat_cells = "".join(
            _render_count_cell(int(counts.get(cat) or 0))
            for cat, _, _ in DELIVERY_CATEGORY_META
        )
        parts.append(
            f"""            <tr data-search="{_esc(row['search'])}">
            <td class="col-id">{_esc(row['patient_id'])}</td>
            <td class="col-name" title="{_esc(row['patient_name'])}">{_esc(row['patient_name'])}</td>
            <td class="col-phone">{_esc(row['phone'])}</td>
            <td class="col-email" title="{_esc(row['email'])}">{_esc(row['email'])}</td>
            <td class="num total-col">{row['total_files']}</td>
            {cat_cells}
            </tr>"""
        )
    return "\n".join(parts)


def generate_progress_report(
    facility_name: str,
    patient_data: List[Dict[str, str]],
    base_downloads_path: str,
    output_dir: str,
    to_pascalcase,
    custom_filename: str = None,
) -> str:
    """
    Scan downloads for every patient in the CSV and write a shareable delivery HTML report.
    Returns path to the HTML file.
    """
    rows = _build_delivery_rows(patient_data, base_downloads_path, to_pascalcase)
    category_totals = _summarize_category_totals(rows)
    total_patients = len(rows)
    total_files = sum(row["total_files"] for row in rows)

    os.makedirs(output_dir, exist_ok=True)
    if not custom_filename:
        custom_filename = delivery_report_filename(facility_name)

    out_path = os.path.join(output_dir, custom_filename)
    delivery_date = datetime.now().strftime("%B %d, %Y")
    year = datetime.now().year

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(facility_name)} Data Export Delivery</title>
  <style>
    :root {{
      --bg: #f3f6fa;
      --card: #ffffff;
      --ink: #152033;
      --muted: #5a6b7d;
      --line: #e2e8f0;
      --accent: #0b4f7a;
      --accent-soft: #e8f2f8;
      --row-h: 38px;
      --head-h: 50px;
      --visible-rows: 20;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      background: linear-gradient(180deg, #dfeaf3 0%, var(--bg) 28%);
      color: var(--ink);
      line-height: 1.5;
      min-height: 100vh;
    }}
    .wrap {{
      width: 100%;
      max-width: 1400px;
      margin: 0 auto;
      padding: 20px 36px 36px;
    }}
    header.hero {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px 22px;
      box-shadow: 0 8px 22px rgba(11, 79, 122, 0.07);
      margin-bottom: 12px;
    }}
    .brand {{
      font-size: 0.78rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--accent);
      font-weight: 700;
      margin-bottom: 6px;
    }}
    header.hero h1 {{
      margin: 0 0 8px;
      font-size: 1.55rem;
      color: var(--accent);
      line-height: 1.5;
    }}
    header.hero .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 22px;
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.5;
    }}
    header.hero .meta strong {{ color: var(--ink); font-weight: 600; }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin-bottom: 12px;
    }}
    .kpi {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px 14px;
      box-shadow: 0 3px 10px rgba(0,0,0,0.03);
    }}
    .kpi .label {{
      font-size: 0.8rem;
      color: var(--muted);
      font-weight: 600;
      line-height: 1.5;
    }}
    .kpi .value {{
      margin-top: 2px;
      font-size: 1.7rem;
      font-weight: 700;
      color: var(--accent);
      line-height: 1.3;
    }}
    .section {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px 16px;
      margin-bottom: 12px;
      box-shadow: 0 3px 10px rgba(0,0,0,0.03);
    }}
    .section h2 {{
      margin: 0 0 4px;
      font-size: 1.15rem;
      color: var(--ink);
      line-height: 1.5;
    }}
    .section .sub {{
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.5;
    }}
    .vol-grid {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 8px;
      margin-bottom: 12px;
    }}
    @media (max-width: 1000px) {{
      .vol-grid {{ grid-template-columns: repeat(2, 1fr); }}
      .kpis {{ grid-template-columns: 1fr; }}
    }}
    .vol-card {{
      background: var(--accent-soft);
      border-radius: 8px;
      padding: 10px 10px 8px;
      border: 1px solid #d5e6f0;
    }}
    .vol-top {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 8px;
    }}
    .vol-label {{
      font-size: 0.78rem;
      color: var(--muted);
      font-weight: 600;
      line-height: 1.5;
    }}
    .vol-value {{
      font-size: 1.05rem;
      font-weight: 700;
      color: var(--accent);
      line-height: 1.3;
      white-space: nowrap;
    }}
    .vol-track {{
      margin-top: 6px;
      height: 8px;
      background: #d9e7f1;
      border-radius: 999px;
      overflow: hidden;
    }}
    .vol-fill {{
      height: 100%;
      background: linear-gradient(90deg, #0b4f7a, #1a8fc4);
      border-radius: 999px;
    }}
    .vol-unit {{
      margin-top: 4px;
      font-size: 0.72rem;
      color: var(--muted);
      line-height: 1.5;
    }}
    .search-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-bottom: 8px;
    }}
    .search-bar input {{
      flex: 1 1 240px;
      min-width: 180px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      font-size: 0.9rem;
      outline: none;
      background: #fff;
      line-height: 1.5;
    }}
    .search-bar input:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(11, 79, 122, 0.12);
    }}
    .search-meta {{
      font-size: 0.85rem;
      color: var(--muted);
      white-space: nowrap;
      line-height: 1.5;
    }}
    .table-wrap {{
      overflow-x: auto;
      overflow-y: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      max-height: calc(var(--head-h) + (var(--visible-rows) * var(--row-h)));
      width: 100%;
    }}
    table {{
      width: max-content;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 0.86rem;
      line-height: 1.5;
    }}
    th, td {{
      padding: 6px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: middle;
      white-space: nowrap;
    }}
    th {{
      position: sticky;
      top: 0;
      background: var(--accent);
      color: #fff;
      font-weight: 600;
      z-index: 2;
      height: var(--head-h);
      line-height: 1.5;
      white-space: normal;
      font-size: 0.78rem;
      padding: 6px 8px;
    }}
    th .h-main {{ display: block; white-space: nowrap; }}
    th .h-fmt {{
      display: block;
      font-weight: 500;
      font-size: 0.7rem;
      opacity: 0.92;
      margin-top: 0;
      line-height: 1.5;
    }}
    tbody tr {{ height: var(--row-h); }}
    tbody tr:nth-child(even) td {{ background: #f8fafc; }}
    tbody tr:hover td {{ background: #eef6fb; }}
    td.num, th.num {{ text-align: center; font-variant-numeric: tabular-nums; }}
    td.zero {{ color: #94a3b8; }}
    td.total-col {{ font-weight: 700; color: var(--accent); }}
    th:nth-child(1), td.col-id {{ width: 84px; }}
    th:nth-child(2), td.col-name {{ width: 140px; max-width: 140px; overflow: hidden; text-overflow: ellipsis; }}
    th:nth-child(3), td.col-phone {{ width: 126px; }}
    th:nth-child(4), td.col-email {{ width: 170px; max-width: 170px; overflow: hidden; text-overflow: ellipsis; }}
    th:nth-child(5), td.total-col {{ width: 78px; }}
    th.cat-h, td.num {{ width: 74px; padding-left: 4px; padding-right: 4px; }}
    footer.site-footer {{
      margin-top: 16px;
      padding: 14px 8px 4px;
      text-align: center;
      color: var(--muted);
      font-size: 0.85rem;
      border-top: 1px solid var(--line);
      line-height: 1.5;
    }}
    footer.site-footer .tagline {{
      font-weight: 600;
      color: var(--accent);
      margin-bottom: 2px;
    }}
    footer.site-footer .copy {{
      font-size: 0.8rem;
    }}
    @media print {{
      body {{ background: #fff; }}
      .table-wrap {{ max-height: none; overflow: visible; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <div class="brand">Calysta Pro EMR · Facility Data Export</div>
      <h1>{_esc(facility_name)}</h1>
      <div class="meta">
        <div>Delivery Date: <strong>{delivery_date}</strong></div>
        <div>Patients Exported: <strong>{total_patients:,}</strong></div>
        <div>Total Files Delivered: <strong>{total_files:,}</strong></div>
      </div>
    </header>

    <div class="kpis">
      <div class="kpi">
        <div class="label">Total Patients</div>
        <div class="value">{total_patients:,}</div>
      </div>
      <div class="kpi">
        <div class="label">Total Files</div>
        <div class="value">{total_files:,}</div>
      </div>
      <div class="kpi">
        <div class="label">Data Categories</div>
        <div class="value">10</div>
      </div>
    </div>

    <section class="section">
      <h2>Export Volume By Data Type</h2>
      <p class="sub">Cumulative file counts across all patients. Progress bars show relative share of each data type.</p>
      <div class="vol-grid">
{_render_volume_cards(category_totals)}
      </div>
    </section>

    <section class="section">
      <h2>Patient Breakdown</h2>
      <p class="sub">Each column is the number of files exported for that data type. Empty categories show as 0. Search by Patient Name, Cell Phone, or Email.</p>
      <div class="search-bar">
        <input id="patientSearch" type="search" placeholder="Search By Name, Cell Phone, Or Email" autocomplete="off" />
        <span class="search-meta" id="searchMeta">Showing {total_patients:,} Patients</span>
      </div>
      <div class="table-wrap">
        <table id="patientTable">
          <thead>
            <tr>
              {_render_table_header()}
            </tr>
          </thead>
          <tbody>
{_render_table_rows(rows)}
          </tbody>
        </table>
      </div>
    </section>

    <footer class="site-footer">
      <div class="tagline">Calysta Pro EMR Facility Data Export Delivery</div>
      <div class="copy">All Rights Reserved © calystaproemr.com {year}</div>
    </footer>
  </div>

  <script>
    const totalPatients = {total_patients};

    const searchInput = document.getElementById('patientSearch');
    const searchMeta = document.getElementById('searchMeta');
    const rows = Array.from(document.querySelectorAll('#patientTable tbody tr'));

    function digitsOnly(s) {{
      return (s || '').replace(/\\D+/g, '');
    }}

    function applySearch() {{
      const q = (searchInput.value || '').trim().toLowerCase();
      const qDigits = digitsOnly(q);
      let shown = 0;
      rows.forEach(tr => {{
        const hay = tr.getAttribute('data-search') || '';
        let match = !q;
        if (!match) {{
          match = hay.includes(q);
          if (!match && qDigits.length >= 3) {{
            match = hay.includes(qDigits) || digitsOnly(hay).includes(qDigits);
          }}
        }}
        tr.style.display = match ? '' : 'none';
        if (match) shown += 1;
      }});
      if (!q) {{
        searchMeta.textContent = 'Showing ' + totalPatients.toLocaleString() + ' Patients';
      }} else {{
        searchMeta.textContent = 'Showing ' + shown.toLocaleString() + ' Of ' + totalPatients.toLocaleString() + ' Patients';
      }}
    }}

    searchInput.addEventListener('input', applySearch);
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
