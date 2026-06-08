"""校验店铺首页 Seel AI 支持图标是否可见、可点击，且点击后对话窗口打开（Excel 数据驱动）。"""

import re
from pathlib import Path
from urllib.parse import urlparse

import openpyxl
import pytest
from playwright.sync_api import Page, expect

# class="seel_ai_support_icon inline-block" → 两个 class 同时存在
ICON = ".seel_ai_support_icon.inline-block"
# 对话窗口标题（必定出现的文案）
LIVE_SUPPORT_HEADING = "Live Support"

_EXCEL_NAME = "live_widget登陆店铺.xlsx"


def _excel_path() -> Path:
    return Path(__file__).resolve().parent.parent / _EXCEL_NAME


def _load_shop_rows() -> list[tuple[str, str]]:
    """读取 Excel：第一行表头，A 列 URL，B 列 PASSWORD，其余列忽略。"""
    path = _excel_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"未找到数据文件「{_EXCEL_NAME}」，请放在项目根目录: {path.parent}"
        )
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows: list[tuple[str, str]] = []
        for cells in ws.iter_rows(min_row=2, values_only=True):
            if not cells:
                continue
            url = cells[0]
            pwd = cells[1] if len(cells) > 1 else None
            if url is None or str(url).strip() == "":
                continue
            rows.append(
                (
                    str(url).strip(),
                    "" if pwd is None else str(pwd).strip(),
                )
            )
    finally:
        wb.close()
    if not rows:
        raise ValueError(f"「{_EXCEL_NAME}」中没有有效数据行（从第 2 行起，A 列需填写 URL）")
    return rows


def _row_id(url: str, index: int) -> str:
    host = urlparse(url).netloc or url
    safe = host.replace("/", "_")[:60]
    return f"{index}-{safe}"


_SHOP_ROWS = _load_shop_rows()
_ROW_IDS = [_row_id(u, i) for i, (u, _) in enumerate(_SHOP_ROWS, start=1)]


def _dismiss_blocking_overlays(page: Page) -> None:
    """尽量消除广告/订阅/弹窗遮挡。各店铺主题不同，无法 100% 覆盖，失败会忽略。

    策略：先 Esc（多数弹层可关）→ 再尝试点常见关闭按钮。
    """
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)

    # 常见无障碍「关闭」按钮（可按你们实际店铺再补充选择器）
    for sel in (
        'button[aria-label="Close"]',
        'button[aria-label="close"]',
        '[aria-label="Close"]',
        'button[aria-label="關閉"]',
        '[data-testid="close-button"]',
        "dialog button.close",
    ):
        btn = page.locator(sel).first
        try:
            btn.click(timeout=900)
            page.wait_for_timeout(150)
        except Exception:
            continue


def _enter_store_if_password_page(page: Page, store_password: str) -> None:
    if "/password" not in page.url:
        return
    if not store_password:
        pytest.fail("当前店铺在密码页，但 Excel 中该行的 PASSWORD（B 列）为空")
    page.locator("#password").fill(store_password)
    page.get_by_role("button", name="Enter").click()
    expect(page).not_to_have_url(re.compile(r"/password"), timeout=30_000)


@pytest.mark.parametrize(
    "shop_url,store_password",
    _SHOP_ROWS,
    ids=_ROW_IDS,
)
def test_support_icon_is_visible_and_clickable(
    page: Page, shop_url: str, store_password: str
) -> None:
    page.goto(shop_url, wait_until="domcontentloaded")
    _enter_store_if_password_page(page, store_password)
    # 等主题脚本把弹窗挂上来一小会儿，再尝试关掉
    page.wait_for_timeout(800)
    _dismiss_blocking_overlays(page)

    icon = page.locator(ICON).first
    expect(icon).to_be_visible(timeout=30_000)
    box = icon.bounding_box()
    assert box is not None
    assert box["width"] > 0 and box["height"] > 0
    icon.scroll_into_view_if_needed()
    _dismiss_blocking_overlays(page)
    try:
        icon.click(timeout=20_000)
    except Exception:
        # 仍被透明层/广告挡住时，强制点图标中心（可能点在浮层下，仅作兜底）
        _dismiss_blocking_overlays(page)
        icon.scroll_into_view_if_needed()
        icon.click(timeout=20_000, force=True)
    dialog_title = page.get_by_role("heading", name=LIVE_SUPPORT_HEADING)
    expect(dialog_title).to_be_visible(timeout=30_000)
    page.wait_for_timeout(3_000)
