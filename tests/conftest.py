"""pytest 钩子：用例失败时附加截图与录屏到 Allure。"""

from __future__ import annotations

from pathlib import Path

import allure
import pytest
from playwright.sync_api import Page


@pytest.fixture
def browser_context_args(browser_context_args, tmp_path):
    """每个用例在独立 context 里录屏（失败时写入 Allure）。"""
    video_dir = tmp_path / "videos"
    video_dir.mkdir(exist_ok=True)
    return {
        **browser_context_args,
        "record_video_dir": str(video_dir),
    }


@pytest.fixture
def page(page: Page, request: pytest.FixtureRequest):
    def attach_failure_video() -> None:
        rep = getattr(request.node, "rep_call", None)
        if not rep or not rep.failed:
            return
        try:
            video = page.video
            if not video:
                return
            path = video.path()
            if not path or not Path(path).is_file():
                return
            allure.attach.file(
                path,
                name="用例失败录屏",
                attachment_type=allure.attachment_type.WEBM,
                extension="webm",
            )
        except Exception:
            return

    request.addfinalizer(attach_failure_video)
    yield page


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> None:
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)
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
