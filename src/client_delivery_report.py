"""Client facing delivery HTML: totals, volume chart, per patient file counts."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List

from export_status import (
    ALL_CATEGORIES,
    STATUS_DONE_EMPTY,
    folder_file_summary,
    load_export_status,
    DONE_STATES,
)

# Chart / volume card labels (Title Case, no hyphens)
CATEGORY_CLIENT = {
    "01_Patient_Details": "Patient Details",
    "02_Patient_Images": "Images",
    "03_Appointment_History": "Appointments",
    "04_Service_History": "Services",
    "05_Encounter_History": "Encounters",
    "06_Consent_Form_History": "Consents",
    "07_Patient_Invoices": "Invoices",
    "08_Membership_Invoices": "Membership Invoices",
    "09_Available_Credits": "Available Credits",
    "10_SMS_Log_History": "SMS Log",
}

# Breakdown table headers (Title Case + file type)
CATEGORY_TABLE = {
    "01_Patient_Details": ("Patient Details", "CSV"),
    "02_Patient_Images": ("Images", "JPG"),
    "03_Appointment_History": ("Appointments", "CSV"),
    "04_Service_History": ("Services", "CSV"),
    "05_Encounter_History": ("Encounters", "PDF"),
    "06_Consent_Form_History": ("Consents", "PDF"),
    "07_Patient_Invoices": ("Invoices", "PDF"),
    "08_Membership_Invoices": ("Membership Invoices", "PDF"),
    "09_Available_Credits": ("Available Credits", "CSV"),
    "10_SMS_Log_History": ("SMS Log", "CSV"),
}


def _file_count_for_category(patient_folder: str, category: str) -> int:
    """
    Return exported file count for one category.
    Empty ok / no records → 0 so the client sees a clear zero.
    Otherwise count content files on disk (authoritative).
    """
    if not os.path.isdir(patient_folder):
        return 0

    status = load_export_status(patient_folder)
    info = (status.get("categories") or {}).get(category) or {}
    state = info.get("state")

    if state == STATUS_DONE_EMPTY:
        return 0

    sub = os.path.join(patient_folder, category)
    disk_count, _ = folder_file_summary(sub)
    if disk_count > 0:
        return disk_count

    if state in DONE_STATES:
        return int(info.get("files") or 0)
    return 0


def _display_or_dash(value: str) -> str:
    v = (value or "").strip()
    if not v or v.upper() in {"N/A", "NULL", "NONE"}:
        return "—"
    return v


def _digits_only(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _cell_phone_only(patient: Dict[str, str]) -> str:
    """
    Cell phone only (never home phone).
    Patient list CSV maps cell to work_phone / cell_phone.
    """
    for key in ("cell_phone", "work_phone"):
        v = (patient.get(key) or "").strip()
        if v and v.upper() not in {"N/A", "NULL", "NONE"}:
            return v
    return ""


def build_client_rows(
    patient_data: List[Dict[str, str]],
    base_downloads_path: str,
    to_pascalcase,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for p in patient_data:
        pid = str(p["id"]).strip()
        first = to_pascalcase(p["first_name"])
        last = to_pascalcase(p["last_name"])
        folder = os.path.join(base_downloads_path, f"{pid}_{first}_{last}")
        counts = {cat: _file_count_for_category(folder, cat) for cat in ALL_CATEGORIES}
        total_files = sum(counts.values())
        email = (p.get("email") or "").strip()
        cell_phone = _cell_phone_only(p)
        rows.append(
            {
                "patient_id": pid,
                "first_name": first,
                "last_name": last,
                "patient_name": f"{first} {last}",
                "email": email,
                "cell_phone": cell_phone,
                "counts": counts,
                "total_files": total_files,
                "phone_digits": _digits_only(cell_phone),
            }
        )

    rows.sort(
        key=lambda r: (
            (r.get("first_name") or "").casefold(),
            (r.get("last_name") or "").casefold(),
            r.get("patient_id") or "",
        )
    )
    return rows


def cumulative_volumes(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    totals = {cat: 0 for cat in ALL_CATEGORIES}
    for r in rows:
        for cat in ALL_CATEGORIES:
            totals[cat] += int((r.get("counts") or {}).get(cat) or 0)
    return totals


def generate_client_delivery_report(
    facility_name: str,
    patient_data: List[Dict[str, str]],
    base_downloads_path: str,
    output_dir: str,
    to_pascalcase,
    custom_filename: str = None,
    delivery_date: datetime = None,
) -> str:
    """
    Write a client facing HTML delivery summary.
    Shows total patients, cumulative file volumes by category, and per patient counts.
    """
    delivery_date = delivery_date or datetime.now()
    rows = build_client_rows(patient_data, base_downloads_path, to_pascalcase)
    volumes = cumulative_volumes(rows)
    total_patients = len(rows)
    total_files = sum(volumes.values())

    os.makedirs(output_dir, exist_ok=True)
    if not custom_filename:
        safe = "".join(c if c.isalnum() or c in " _-" else "" for c in facility_name).strip()
        safe = safe.replace(" ", "_") or "Facility"
        custom_filename = f"{safe}_Client_Delivery_Report_{delivery_date.strftime('%m-%d-%Y')}.html"

    out_path = os.path.join(output_dir, custom_filename)

    cat_volumes = [volumes[c] for c in ALL_CATEGORIES]
    max_vol = max(max(cat_volumes), 1) if cat_volumes else 1
    table_headers = "".join(
        f'<th class="num cat-h" title="{_esc(name)} ({fmt})">'
        f'<span class="h-main">{_esc(name)}</span>'
        f'<span class="h-fmt">({_esc(fmt)})</span></th>'
        for name, fmt in (CATEGORY_TABLE[c] for c in ALL_CATEGORIES)
    )

    volume_cards = "".join(
        f"""<div class="vol-card">
          <div class="vol-top">
            <div class="vol-label">{_esc(CATEGORY_CLIENT[cat])}</div>
            <div class="vol-value">{volumes[cat]:,}</div>
          </div>
          <div class="vol-track" aria-hidden="true">
            <div class="vol-fill" style="width:{min(100.0, round(100.0 * volumes[cat] / max_vol, 2))}%"></div>
          </div>
          <div class="vol-unit">Files</div>
        </div>"""
        for cat in ALL_CATEGORIES
    )

    table_body = []
    for r in rows:
        cells = "".join(
            f'<td class="num {"zero" if r["counts"][cat] == 0 else ""}">{r["counts"][cat]}</td>'
            for cat in ALL_CATEGORIES
        )
        email_disp = _display_or_dash(r["email"])
        cell_disp = _display_or_dash(r["cell_phone"])
        search_blob = " ".join(
            [
                r["patient_id"],
                r["patient_name"],
                r.get("email") or "",
                r.get("cell_phone") or "",
                r.get("phone_digits") or "",
            ]
        ).lower()
        table_body.append(
            f"""<tr data-search="{_esc(search_blob)}">
            <td class="col-id">{_esc(r['patient_id'])}</td>
            <td class="col-name" title="{_esc(r['patient_name'])}">{_esc(r['patient_name'])}</td>
            <td class="col-phone">{_esc(cell_disp)}</td>
            <td class="col-email" title="{_esc(email_disp)}">{_esc(email_disp)}</td>
            <td class="num total-col">{r['total_files']}</td>
            {cells}
            </tr>"""
        )

    delivery_display = delivery_date.strftime("%B %d, %Y")
    year = delivery_date.year

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
    .note {{
      margin-top: 10px;
      font-size: 0.85rem;
      color: var(--muted);
      background: #f8fafc;
      border-radius: 8px;
      padding: 8px 10px;
      border: 1px solid var(--line);
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
    /* Fixed compact widths so Name/Email do not stretch to longest value */
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
        <div>Delivery Date: <strong>{_esc(delivery_display)}</strong></div>
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
        <div class="value">{len(ALL_CATEGORIES)}</div>
      </div>
    </div>

    <section class="section">
      <h2>Export Volume By Data Type</h2>
      <p class="sub">Cumulative file counts across all patients. Progress bars show relative share of each data type.</p>
      <div class="vol-grid">
        {volume_cards}
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
              <th>Patient ID</th>
              <th>Name</th>
              <th>Cell Phone</th>
              <th>Email</th>
              <th class="num">Total Files</th>
              {table_headers}
            </tr>
          </thead>
          <tbody>
            {''.join(table_body)}
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
