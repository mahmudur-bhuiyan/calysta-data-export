# Project Notes

**Read this file first** before acting on user commands for this repo.

The user maintains project-specific instructions here. When a new task matches a section below, follow that section **before** improvising.

More commands will be added over time.

---

## How agents should use this file

1. Check whether the user's request matches any command section in this file.
2. If it matches, follow that section exactly.
3. If it does not match yet, use normal project code/README behavior.
4. When the user adds a new command here later, treat it as the source of truth for that workflow.

---

## Commands

### `use playwright` / browser testing / check portal in browser

Use when the user asks to **test with Playwright**, **open the portal**, **check a patient page**, or **verify SMS/email logs in the UI**.

#### Decision order

1. **Check MCP browser tools first** (preferred)
2. **If MCP is unavailable**, use local Playwright Python scripts
3. **If Playwright fails because Chromium is missing**, install Chromium, then retry
4. **Only use responsive/mobile viewports when the task explicitly needs it**

Do **not** jump straight to `playwright install` if Cursor browser MCP is available.

#### 1) MCP browser (first choice)

Check availability with `GetDynamicTools`:

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

#### Large-screen default (desktop testing)

For Calysta portal checks, use a **large desktop viewport** so tables, side panels, and patient dashboards render fully.

Project default (from `config/settings.yaml`):

```yaml
viewport:
  width: 1725
  height: 973
```

When using Cursor browser MCP:

- Prefer full desktop width first
- Use `browser_snapshot` + screenshot before concluding something is missing
- If needed, set size via CDP `Emulation.setDeviceMetricsOverride` with width `1725` and height `973`
- Clear emulation when done: `Emulation.clearDeviceMetricsOverride`

#### Responsive testing (only when required)

Use smaller viewports **only** when the user asks for mobile/tablet/responsive behavior.

| Device | Width | Height |
|---|---:|---:|
| Desktop (default) | 1725 | 973 |
| Laptop | 1366 | 768 |
| Tablet | 768 | 1024 |
| Mobile | 390 | 844 |

Rules:

- Test desktop first unless the task is specifically about responsive UI
- Change viewport, re-snapshot, then compare behavior
- Device emulation via CDP lasts for the current turn — clear it before finishing

#### 2) Local Playwright Python (fallback)

Use project scripts under `src/` when MCP is not available or when reproducing export behavior exactly.

**Common entry points**

- Auth/login: `src/auth.py` → `authenticate_and_select_facility()`
- Patient view: `https://www.calystaproemr.com/patients/view/{patient_id}`
- SMS conversation page: `https://www.calystaproemr.com/sms-details/index/{patient_id}` (`src/sms_log_selectors.py`)

**Run**

```bash
cd src
python3 your_probe_script.py
```

Use `config/credentials.yaml` and `config/settings.yaml` (gitignored). Do not commit credentials.

**Viewport for local Playwright**

```python
viewport = settings.get("viewport", {"width": 1725, "height": 973})
context = await browser.new_context(viewport=viewport)
```

For headed debugging, set `browser_mode: headed` in `config/settings.yaml`.

#### 3) Install Chromium (only if local Playwright fails)

If local Playwright errors with:

```text
BrowserType.launch: Executable doesn't exist ...
Please run: playwright install
```

Then run:

```bash
python3 -m playwright install chromium
```

Retry after install. If install is blocked, switch to **Cursor browser MCP** instead of retrying repeatedly.

#### Calysta-specific checks

**Patient dashboard**

```text
https://www.calystaproemr.com/patients/view/{patient_id}
```

Look for SMS/email/notification links, tabs, tables, and chat UI.

**SMS details page**

```text
https://www.calystaproemr.com/sms-details/index/{patient_id}
```

Selectors (`src/sms_log_selectors.py`):

- Chat container: `.entire-chat-bot`
- Message bubbles: `.entire-chat-bot .single-chat-bot`
- Patient messages: `.sender-chat`
- Facility messages: `.receiver-chat`
- Timestamps: `.time-right`

**Export note:** All patient export categories (details, images, appointments, services, encounters, consents, invoices, credits, SMS) are scraped from the live Calysta portal. Master Data is optional and only receives a copy of the patient list for delivery — exports do not read from Master Data.

**Empty folders:** After each patient (and at export start), category folders with no real files are removed. This includes header-only CSVs, zero-byte PDFs/images, and legacy placeholder CSVs. Credits and patient details are kept when export succeeds; all other categories are omitted when empty.

#### Evidence to save

Save probe output under:

```text
downloads/logs/<probe-name>/
```

Recommended artifacts:

- `*.png` screenshots (dashboard + SMS page)
- `*.json` structured probe result (message count, sample text, empty-state hints)
- Short summary: URL checked, messages found (yes/no), count, blockers

#### Quick checklist

- [ ] Checked MCP browser namespaces (`cursor-ide-browser` first)
- [ ] Opened target in Cursor browser tab (large desktop viewport)
- [ ] Took snapshot and screenshot
- [ ] Checked patient dashboard **and** SMS details URL if relevant
- [ ] Used responsive viewport only if task required it
- [ ] Fell back to local Playwright only when MCP unavailable
- [ ] Ran `python3 -m playwright install chromium` only after executable-missing error
- [ ] Saved notes/screenshots under `downloads/logs/`

---

## Future commands

Add new sections above this line as the project grows.

Example format:

```md
### `your command here`

Use when ...

#### Steps
1. ...
2. ...
```
