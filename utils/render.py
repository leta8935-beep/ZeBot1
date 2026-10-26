import pathlib
import json
from playwright.async_api import async_playwright

async def render_template(template_name: str, data: dict) -> bytes:
    tpl_path = pathlib.Path(__file__).parent.parent / "templates" / template_name
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        
        # Жестко задаем область 720x1000 и включаем 2x рендеринг для четкости
        context = await browser.new_context(
            viewport={"width": 720, "height": 1000},
            device_scale_factor=2 
        )
        page = await context.new_page()
        
        await page.goto(f"file://{tpl_path.resolve()}")
        await page.evaluate(f"window.renderData({json.dumps(data)})")
        
        try:
            # Ждем, пока прогрузятся шрифты и картинки
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
            
        await page.wait_for_timeout(500) 
        
        # Делаем скриншот именно тела страницы
        png_bytes = await page.locator("body").screenshot()
        await browser.close()
        return png_bytes
