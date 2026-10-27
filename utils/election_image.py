from pathlib import Path
from playwright.async_api import async_playwright

TEMPLATE = Path(__file__).parent.parent / 'templates' / 'election_template.html'

_playwright = None
_browser = None


async def _get_browser():
    global _playwright, _browser
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(args=['--no-sandbox'])
    return _browser


async def render_election_image(data: dict) -> bytes:
    browser = await _get_browser()
    context = await browser.new_context(viewport={'width': 1100, 'height': 900}, device_scale_factor=2)
    page = await context.new_page()
    await page.goto(TEMPLATE.as_uri())
    await page.evaluate('(d) => window.renderElection(d)', data)
    await page.wait_for_timeout(700)
    element = await page.query_selector('.workspace')
    img = await element.screenshot(type='png')
    await context.close()
    return img


async def shutdown():
    global _playwright, _browser
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
