# Handles login, facility selection, and session management


import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from login_selectors import USERNAME_FIELD, PASSWORD_FIELD, LOGIN_BUTTON, ERROR_MESSAGE

async def authenticate_and_select_facility(credentials, settings):
    """
    Authenticates to the EMR system and selects the facility.
    Returns: playwright browser, context, and page objects after successful login and facility selection.
    """
    base_url = settings.get('base_url', 'https://www.calystaproemr.com')
    browser_mode = settings.get('browser_mode', 'headless')
    page_timeout = int(settings.get('page_timeout', 30000))

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=(browser_mode == 'headless'))
    viewport = settings.get('viewport', {"width": 1280, "height": 720})
    context = await browser.new_context(viewport=viewport)
    page = await context.new_page()

    # One shared dialog handler for the whole session.
    # Downloaders must NOT register additional handlers — that causes
    # "Cannot accept dialog which is already handled" races.
    async def _auto_accept_dialog(dialog):
        try:
            await dialog.accept()
        except Exception:
            pass  # already handled by another accept path

    page.on("dialog", _auto_accept_dialog)

    # Go to login page
    login_url = base_url
    await page.goto(login_url, timeout=page_timeout)


    # Fill username and password using Playwright codegen selectors
    await page.wait_for_selector(USERNAME_FIELD, timeout=page_timeout)
    await page.fill(USERNAME_FIELD, credentials['username'])
    await page.fill(PASSWORD_FIELD, credentials['password'])
    await page.click(LOGIN_BUTTON)
    # Wait for post-login UI (avoid networkidle — portals often keep polling)
    try:
        await page.wait_for_selector('#global-facility, .page-wrapper, .dashboard', timeout=page_timeout)
    except PlaywrightTimeoutError:
        try:
            await page.wait_for_load_state('domcontentloaded', timeout=5000)
        except PlaywrightTimeoutError:
            pass
    # Check login success
    url = page.url
    if not (any(x in url for x in ['/dashboard', '/main', '/home']) or not url.endswith('/login')):
        # Check for error message
        error_text = ''
        try:
            error_elem = await page.query_selector(ERROR_MESSAGE)
            if error_elem:
                error_text = await error_elem.inner_text()
        except Exception:
            pass
        await browser.close()
        raise Exception(f"Login failed. {error_text}")

    # Facility selection (if required)
    facility = credentials.get('facility')
    if facility:
        try:
            # Wait for the facility select to be present
            await page.wait_for_selector('#global-facility', timeout=page_timeout)
            select_el = await page.query_selector('#global-facility')
            options = await select_el.query_selector_all('option')
            found = False
            for option in options:
                title = (await option.get_attribute('title') or '').lower()
                text = (await option.inner_text() or '').lower()
                if facility.lower() in title:
                    await select_el.select_option(value=await option.get_attribute('value'))
                    found = True
                    break
                if facility.lower() in text:
                    await select_el.select_option(value=await option.get_attribute('value'))
                    found = True
                    break
            if not found:
                # Try matching by value (numeric id)
                try:
                    await select_el.select_option(value=facility)
                    found = True
                except Exception:
                    pass
            if not found:
                raise Exception(f"Facility '{facility}' not found in global-facility select")
            # Small wait for selection to take effect
            await asyncio.sleep(0.5)
        except Exception as e:
            raise Exception(f"Error selecting facility '{facility}': {e}")

    return playwright, browser, context, page
