---
name: calysta-export-project
description: >-
  Calysta Data Export repo workflow. Use for any task in this project — export
  patients, update patient_lists CSVs, run_export.py, portal browser checks,
  Playwright probes, SMS logs, validate exports, or when the user mentions
  Calysta, facility export, or patient_lists.
---

# Calysta Export Project

**Read this skill first** before acting on user commands for this repo.

When a new workflow is needed, extend this skill — it is the source of truth for project-specific agent behavior.

## Bulk export workflow

When the user asks to export patients:

1. Confirm or build the patient list CSV in **`patient_lists/`** (required columns: `id`, `first_name`, `last_name`).
2. Filename must **match** `facility` in `config/credentials.yaml` (spaces/hyphens/underscores ignored).
3. Run: `python3 run_export.py` or `./export` from project root.
4. Output: `downloads/<Facility Name>/` with **Patients Records** and **Delivery Report** only.
5. Exports scrape the **live portal** — not Master Data.
6. **Master Data is off-limits** — the exporter never reads from or writes to `... - Master Data/`. The user manages that folder manually.

**Building a patient list:** Use `patient_lists/` only. If the user has a reference CSV elsewhere (e.g. under Master Data), copy or subset rows into `patient_lists/` yourself — do not expect the exporter to touch Master Data.

**Resume behavior:** Already-complete patients in `export_index.csv` are skipped; only pending patients are processed.

**Empty folders:** After each patient (and at export start), category folders with no real files are removed. Credits and patient details are kept when export succeeds; all other categories are omitted when empty.

## Browser / portal / Playwright

Use when the user asks to **test with Playwright**, **open the portal**, **check a patient page**, or **verify SMS/email logs in the UI**.

### Decision order

1. **Check MCP browser tools first** (preferred)
2. **If MCP is unavailable**, use local Playwright Python scripts
3. **If Playwright fails because Chromium is missing**, install Chromium, then retry
4. **Only use responsive/mobile viewports when the task explicitly needs it**

**Never jump straight to `playwright install` if Cursor browser MCP is available.**

| Step | When | Action |
|------|------|--------|
| 1 | Any portal check, UI verify, or browser task | `GetDynamicTools` → check `cursor-ide-browser` (first), then `plugin-playwright-playwright` |
| 2 | MCP ready | Use MCP browser workflow below |
| 3 | MCP unavailable or need exact export script behavior | Local Playwright under `src/` |
| 4 | Local Playwright fails with missing Chromium executable | `python3 -m playwright install chromium`, then retry once |
| 5 | Install blocked | Stop retrying; report blocker; use MCP if still needed |

### MCP browser (first choice)

| Namespace | When to use |
|---|---|
| `cursor-ide-browser` | Default — Cursor-owned browser tab in the IDE |
| `plugin-playwright-playwright` | Fallback if Cursor browser MCP is not available |

If `namespaceStatus` is `needsAuth`, authenticate that MCP server first, then retry.

**Cursor browser workflow**

1. `browser_tabs` → `action: "list"` — see open tabs and URLs
2. `browser_navigate` → open the target URL in a **new tab** (or reuse an existing tab)
3. `browser_lock` → `action: "lock"` before longer automation
4. `browser_snapshot` — read page structure (main source of truth)
5. Interact with `browser_click`, `browser_fill`, `browser_type`, `browser_scroll`, etc.
6. `browser_take_screenshot` — visual proof when needed
7. `browser_lock` → `action: "unlock"` when finished

**Lock order**

- New tab: `browser_navigate` → `browser_lock(lock)` → actions → `browser_lock(unlock)`
- Existing tab: `browser_lock(lock)` first, then act

**Stop and report** if login, MFA, captcha, or manual approval is required — do not loop retries.

### Viewport

Default desktop viewport (from `config/settings.yaml`): **1725 × 973**.

When using Cursor browser MCP:

- Prefer full desktop width first
- Use `browser_snapshot` + screenshot before concluding something is missing
- If needed, set size via CDP `Emulation.setDeviceMetricsOverride` with width `1725` and height `973`
- Clear emulation when done: `Emulation.clearDeviceMetricsOverride`

**Responsive testing** — only when the user asks for mobile/tablet/responsive behavior:

| Device | Width | Height |
|---|---:|---:|
| Desktop (default) | 1725 | 973 |
| Laptop | 1366 | 768 |
| Tablet | 768 | 1024 |
| Mobile | 390 | 844 |

### Local Playwright (fallback)

Use project scripts under `src/` when MCP is not available or when reproducing export behavior exactly.

**Common entry points**

- Auth/login: `src/auth.py` → `authenticate_and_select_facility()`
- Patient view: `https://www.calystaproemr.com/patients/view/{patient_id}`
- SMS conversation page: `https://www.calystaproemr.com/sms-details/index/{patient_id}` (`src/sms_log_selectors.py`)

```bash
cd src
python3 your_probe_script.py
```

Use `config/credentials.yaml` and `config/settings.yaml` (gitignored). Do not commit credentials.

For headed debugging, set `browser_mode: headed` in `config/settings.yaml`.

### Install Chromium (only if local Playwright fails)

If local Playwright errors with `BrowserType.launch: Executable doesn't exist`:

```bash
python3 -m playwright install chromium
```

Retry after install. If install is blocked, switch to **Cursor browser MCP** instead of retrying repeatedly.

### Calysta-specific checks

**Patient dashboard:** `https://www.calystaproemr.com/patients/view/{patient_id}` — look for SMS/email/notification links, tabs, tables, and chat UI.

**SMS details page:** `https://www.calystaproemr.com/sms-details/index/{patient_id}`

Selectors (`src/sms_log_selectors.py`):

- Chat container: `.entire-chat-bot`
- Message bubbles: `.entire-chat-bot .single-chat-bot`
- Patient messages: `.sender-chat`
- Facility messages: `.receiver-chat`
- Timestamps: `.time-right`

### Evidence to save

Save probe output under `downloads/logs/<probe-name>/`:

- `*.png` screenshots (dashboard + SMS page)
- `*.json` structured probe result (message count, sample text, empty-state hints)
- Short summary: URL checked, messages found (yes/no), count, blockers

## Key paths

| Path | Purpose |
|------|---------|
| `patient_lists/` | Input CSVs for export (only location used) |
| `config/credentials.yaml` | Login + facility name (gitignored) |
| `config/settings.yaml` | Browser mode, viewport, timeouts |
| `run_export.py` / `./export` | Start bulk export |
| `src/main.py` | Export engine |
| `downloads/logs/` | Execution logs and probe artifacts |

## Rules

- Do **not** commit `config/credentials.yaml`.
- Do **not** create git commits unless the user asks.
- If no skill section matches, use `README.md` and `src/` conventions.

## Quick checklist (browser tasks)

- [ ] Checked MCP browser namespaces (`cursor-ide-browser` first)
- [ ] Opened target in Cursor browser tab (large desktop viewport)
- [ ] Took snapshot and screenshot
- [ ] Checked patient dashboard **and** SMS details URL if relevant
- [ ] Used responsive viewport only if task required it
- [ ] Fell back to local Playwright only when MCP unavailable
- [ ] Ran `python3 -m playwright install chromium` only after executable-missing error
- [ ] Saved notes/screenshots under `downloads/logs/`
