"""pytest 钩子：用例失败时把当前页面截图挂到 Allure。"""

from __future__ import annotations

import allure
import pytest
from playwright.sync_api import Page


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> None:
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call" or not rep.failed:
        return
    page = item.funcargs.get("page") if item.funcargs else None
    if not isinstance(page, Page):
        return
    try:
        png = page.screenshot(full_page=False)
    except Exception:
        return
    allure.attach(
        png,
        name="用例失败截图",
        attachment_type=allure.attachment_type.PNG,
    )
