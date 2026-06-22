"""Excel 驱动：进店 → 尽量关掉弹窗 → 点图标 → 对话窗口出现。"""

import time
from pathlib import Path
from urllib.parse import urlparse

import allure
import openpyxl
import pytest
from playwright.sync_api import Page

ICON = ".seel_ai_support_icon.inline-block"
DIALOG_TITLE = "Live Support"
EXCEL = Path(__file__).resolve().parent.parent / "live_widget登陆店铺.xlsx"

URL_HEADER = "URL"
PWD_HEADER = "PASSWORD"
STATUS_HEADER = "STATUS"


def read_shops() -> list[tuple[str, str]]:
    """读 Excel：第 1 行表头匹配列名（忽略大小写、首尾空格），须含 URL、PASSWORD；有 STATUS 列时仅保留值为 0 的行。"""
    if not EXCEL.is_file():
        raise FileNotFoundError(f"缺少数据文件，请放到项目根目录: {EXCEL.name}")

    def cell_is_status_zero(cell: object) -> bool:
        if cell is None or isinstance(cell, bool):
            return False
        if isinstance(cell, (int, float)):
            return cell == 0
        s = str(cell).strip()
        if not s:
            return False
        try:
            return float(s) == 0.0
        except ValueError:
            return False

    wb = openpyxl.load_workbook(EXCEL, read_only=True, data_only=True)
    try:
        row_iter = wb.active.iter_rows(values_only=True)
        header = next(row_iter, None)
        if header is None:
            raise ValueError("Excel 为空")

        # 表头名 -> 列下标（同名取第一次出现的列）
        col: dict[str, int] = {}
        for i, cell in enumerate(header):
            if cell is None:
                continue
            name = str(cell).strip().casefold()
            if name and name not in col:
                col[name] = i

        for req in (URL_HEADER, PWD_HEADER):
            if req.casefold() not in col:
                seen = [repr(str(h).strip() if h is not None else "") for h in header]
                raise ValueError(
                    f"表头中缺少 {req!r} 列（当前表头: {seen}）。"
                    f"第一行须包含 {URL_HEADER!r} 与 {PWD_HEADER!r}。"
                )

        url_i = col[URL_HEADER.casefold()]
        pwd_i = col[PWD_HEADER.casefold()]
        status_i = col.get(STATUS_HEADER.casefold())

        rows: list[tuple[str, str]] = []
        for cells in row_iter:
            if not cells:
                continue
            if status_i is not None:
                raw_st = cells[status_i] if status_i < len(cells) else None
                if not cell_is_status_zero(raw_st):
                    continue
            if url_i >= len(cells) or not cells[url_i]:
                continue
            url = str(cells[url_i]).strip()
            if not url:
                continue
            raw_pwd = cells[pwd_i] if pwd_i < len(cells) else None
            pwd = "" if raw_pwd is None else str(raw_pwd).strip()
            rows.append((url, pwd))
    finally:
        wb.close()

    if not rows:
        hint = ""
        if status_i is not None:
            hint = f" 若表头含 {STATUS_HEADER!r}，仅 {STATUS_HEADER} 为 0 的行会参与用例。"
        raise ValueError(
            f"Excel 里至少填一行可执行的店铺：非空 {URL_HEADER}，"
            f"且表头须含 {URL_HEADER!r} / {PWD_HEADER!r}。{hint}"
        )
    return rows


SHOPS = read_shops()


def _fail_brief(page: Page, summary: str, *, shop_url: str | None = None) -> None:
    """失败时只输出几行关键信息，避免 expect() 附带整页无障碍树。"""
    lines = [summary.rstrip()]
    if shop_url:
        lines.append(f"表格 URL host: {urlparse(shop_url).netloc!r}")
    lines.append(f"当前 page.url: {page.url!r}")
    lines.append("详情见 Allure「用例失败截图」。")
    pytest.fail("\n".join(lines), pytrace=False)


def _wait_visible(
    page: Page,
    shop_url: str,
    locator,
    *,
    timeout_ms: int,
    summary: str,
) -> None:
    try:
        locator.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        _fail_brief(page, f"{summary}（{timeout_ms // 1000}s 超时）", shop_url=shop_url)


def try_close_popups(page: Page) -> None:
    """Esc + 点常见关闭钮；关不掉就忽略（各店主题不一样）。"""
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


def enter_if_password(page: Page, password: str) -> None:
    if "/password" not in page.url:
        return
    if not password:
        _fail_brief(page, "进了密码页，但 Excel 里该行 PASSWORD 列为空")
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Enter").click()
    deadline = time.monotonic() + 30.0
    while "/password" in page.url:
        if time.monotonic() > deadline:
            _fail_brief(page, "密码页：点 Enter 后 30s 内 URL 仍含 /password")
        page.wait_for_timeout(200)


@pytest.mark.parametrize(
    "shop_url,password",
    SHOPS,
    ids=[urlparse(u).netloc for u, _ in SHOPS],
)
def test_live_widget(page: Page, shop_url: str, password: str) -> None:
    allure.dynamic.title(f"Seel widget — {urlparse(shop_url).netloc}")
    # commit：收到响应、导航提交后即返回，不等待 DOMContentLoaded（部分店极慢但 widget 已注入）
    page.goto(shop_url, wait_until="commit", timeout=60_000)
    enter_if_password(page, password)

    page.wait_for_timeout(600)
    try_close_popups(page)

    icon = page.locator(ICON).first
    _wait_visible(
        page,
        shop_url,
        icon,
        timeout_ms=90_000,
        summary=f"未看到 Seel 图标（选择器 {ICON!r}）",
    )
    icon.scroll_into_view_if_needed()
    try_close_popups(page)

    try:
        icon.click(timeout=20_000)
    except Exception:
        try_close_popups(page)
        try:
            icon.click(timeout=20_000, force=True)
        except Exception:
            _fail_brief(page, "点击 Seel 图标失败（含 force 重试）", shop_url=shop_url)

    _wait_visible(
        page,
        shop_url,
        page.get_by_role("heading", name=DIALOG_TITLE),
        timeout_ms=30_000,
        summary=f"点击图标后未出现对话标题 {DIALOG_TITLE!r}（heading）",
    )
    page.wait_for_timeout(3_000)
    allure.attach(
        page.screenshot(full_page=False),
        name="Widget已打开",
        attachment_type=allure.attachment_type.PNG,
    )
