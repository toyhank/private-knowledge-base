"""Optional UI verification: use a Python environment with playwright installed."""

import json
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[1]
out = root / "test-results"
out.mkdir(exist_ok=True)
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 950}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:8000", wait_until="networkidle")
    expect(page.get_by_role("heading", name="让资料，成为答案。")).to_be_visible()
    page.get_by_role("button", name="使用帮助").click()
    expect(page.get_by_role("heading", name="开始使用知屿")).to_be_visible()
    page.get_by_role("button", name="知道了").click()
    page.get_by_role("button", name="北京出差的住宿标准是多少？", exact=True).click()
    expect(page.get_by_role("textbox", name="输入问题")).to_have_value("北京出差的住宿标准是多少？")
    page.screenshot(path=str(out / "desktop.png"), full_page=True)
    if "--chat" in sys.argv:
        page.get_by_role("button", name="发送问题", exact=True).click()
        expect(page.locator(".message.assistant .message-text")).to_contain_text("600", timeout=660_000)
        page.locator(".citations > button").first.click()
        expect(page.get_by_role("dialog")).to_be_visible()
        expect(page.locator(".source-body blockquote")).to_contain_text("600")
        page.screenshot(path=str(out / "citation.png"), full_page=True)
        page.get_by_role("button", name="关闭引用").click()
        page.screenshot(path=str(out / "answer.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(out / "mobile.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
        "Mobile horizontal overflow"
    )
    assert not errors, errors
    (out / "ui-results.json").write_text(
        json.dumps(
            {
                "passed": True,
                "chat": "--chat" in sys.argv,
                "page_errors": errors,
                "viewports": ["1440x950", "390x844"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    browser.close()
    print("UI smoke passed", flush=True)
