"""Excel 驱动：进店 → 关弹窗 → 等图标 → 点图标 → 对话窗口出现。"""

from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlparse

import allure
import openpyxl
import pytest
from playwright.sync_api import Page, expect

ICON = ".seel_ai_support_icon"
DIALOG_TITLE = "Live Support"
ICON_WAIT_MS = 90_000
ICON_CLICK_MS = 90_000
CLICK_RETRY_INTERVAL_MS = 3_000
DIALOG_AFTER_CLICK_MS = 10_000
EXCEL = Path(__file__).resolve().parent.parent / "live_widget登陆店铺.xlsx"

URL_HEADER = "URL"
PWD_HEADER = "PASSWORD"
STATUS_HEADER = "STATUS"
ID_HEADER = "ID"


def read_shops() -> list[tuple[str, str, str]]:
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
        id_i = col.get(ID_HEADER.casefold())

        rows: list[tuple[str, str, str]] = []
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
            raw_id = cells[id_i] if id_i is not None and id_i < len(cells) else None
            shop_id = "" if raw_id is None else str(raw_id).strip()
            rows.append((url, pwd, shop_id))
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


def _fail_brief(
    page: Page,
    summary: str,
    *,
    shop_url: str | None = None,
    shop_id: str | None = None,
) -> None:
    """失败时只输出几行关键信息，避免 expect() 附带整页无障碍树。"""
    lines = [summary.rstrip()]
    if shop_id is not None:
        lines.append(f"当前 ID: {shop_id!r}")
    if shop_url:
        lines.append(f"表格 URL host: {urlparse(shop_url).netloc!r}")
    lines.append(f"当前 page.url: {page.url!r}")
    lines.append("详情见 Allure「用例失败截图」。")
    pytest.fail("\n".join(lines), pytrace=False)


def _icon_locator(page: Page):
    return page.locator(ICON).first


def _is_dialog_open(page: Page) -> bool:
    """判断 widget 对话是否已打开（多种探针，避免 heading role 偶发匹配不到）。"""
    probes = (
        page.get_by_role("heading", name=DIALOG_TITLE),
        page.get_by_text(DIALOG_TITLE, exact=True),
        page.locator("h1").filter(has_text=DIALOG_TITLE),
        page.get_by_placeholder(re.compile(r"type your message", re.I)),
    )
    for probe in probes:
        try:
            if probe.count() > 0 and probe.first.is_visible():
                return True
        except Exception:
            continue
    return False


def _wait_dialog_open(page: Page, timeout_ms: int) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if _is_dialog_open(page):
            return True
        page.wait_for_timeout(200)
    return False


def try_close_popups(page: Page) -> None:
    """Esc + 点常见关闭钮（含 Luck Day / Spin 等营销弹窗）；关不掉就忽略。"""
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)

    for sel in (
        'button[aria-label="Close"]',
        'button[aria-label="close"]',
        '[aria-label="Close"]',
        'button[aria-label="關閉"]',
        '[data-testid="close-button"]',
        "dialog button.close",
        ".close",
        "[class*='close-button']",
        "[class*='modal-close']",
        "[class*='CloseButton']",
    ):
        btn = page.locator(sel).first
        try:
            btn.click(timeout=500)
            page.wait_for_timeout(150)
        except Exception:
            continue

    # Luck Day / Spin to Win 等：文字为 Close、×、No thanks 的可点元素
    text_closers = (
        page.get_by_text(re.compile(r"^x?\s*Close$", re.I)),
        page.get_by_text("✕", exact=True),
        page.get_by_text("×", exact=True),
        page.get_by_text(re.compile(r"^No thanks", re.I)),
        page.get_by_text(re.compile(r"^Skip", re.I)),
        page.locator("span").filter(has_text=re.compile(r"^Close$", re.I)),
    )
    for loc in text_closers:
        try:
            loc.first.click(timeout=500)
            page.wait_for_timeout(150)
        except Exception:
            continue


# 让高 z-index 遮罩不拦截指针事件，使下方 widget 可被点到（不关弹窗也能点图标）
_NEUTRALIZE_OVERLAYS_JS = """
() => {
  const icon = document.querySelector('.seel_ai_support_icon');
  function isSeelTree(el) {
    if (!el || el === document.body) return false;
    const cls = (el.className || '').toString();
    const id = el.id || '';
    if (/seel/i.test(cls) || /seel/i.test(id)) return true;
    if (el.classList?.contains('seel_ai_support_icon')) return true;
    return el.querySelector?.('.seel_ai_support_icon') != null;
  }
  for (const el of document.querySelectorAll('body *')) {
    if (isSeelTree(el)) continue;
    const s = getComputedStyle(el);
    const z = parseInt(s.zIndex, 10);
    if (Number.isNaN(z) || z < 50) continue;
    if (s.position !== 'fixed' && s.position !== 'absolute') continue;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    if (w < window.innerWidth * 0.2 && h < window.innerHeight * 0.2) continue;
    el.style.setProperty('pointer-events', 'none', 'important');
  }
  if (icon) {
    const r = icon.getBoundingClientRect();
    const x = r.left + r.width / 2;
    const y = r.top + r.height / 2;
    let top = document.elementFromPoint(x, y);
    for (let i = 0; i < 8 && top && top !== icon && !icon.contains(top); i++) {
      if (!isSeelTree(top)) {
        top.style.setProperty('pointer-events', 'none', 'important');
      }
      top = document.elementFromPoint(x, y);
    }
  }
}
"""


def _neutralize_overlays_on_icon(page: Page) -> None:
    try:
        page.evaluate(_NEUTRALIZE_OVERLAYS_JS)
    except Exception:
        pass


def settle_after_goto(page: Page) -> None:
    """commit 之后等 DOM 就绪（含自定义域名跳转），便于异步 widget 脚本执行。"""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=45_000)
    except Exception:
        pass


def _click_icon(page: Page, *, force: bool) -> bool:
    """
    点 widget 图标。

    force=False：Playwright 常规点击（元素须可见、稳定、未被遮挡）。
    force=True：跳过上述检查，仍对元素中心发点击。
    返回 False 表示 click 抛错；True 表示 Playwright 认为点击已发出。
    """
    icon = _icon_locator(page)
    try:
        icon.scroll_into_view_if_needed(timeout=2_000)
        icon.click(timeout=3_000, force=force)
        return True
    except Exception:
        return False


def _click_icon_via_js(page: Page) -> bool:
    """在图标元素上直接触发 click（不依赖 Playwright 命中层）。"""
    try:
        _icon_locator(page).evaluate(
            "el => {"
            "el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));"
            "if (typeof el.click === 'function') el.click();"
            "}"
        )
        return True
    except Exception:
        return False


def _click_icon_at_point(page: Page) -> bool:
    """按图标中心屏幕坐标点击（遮罩已 neutralize 后通常能命中 widget）。"""
    try:
        box = _icon_locator(page).bounding_box()
        if not box or box["width"] <= 0 or box["height"] <= 0:
            return False
        page.mouse.click(
            box["x"] + box["width"] / 2,
            box["y"] + box["height"] / 2,
        )
        return True
    except Exception:
        return False


def _attempt_open_widget_click(page: Page) -> None:
    """一轮点击：关弹窗 → 去遮罩 → 普通 / force / JS / 坐标，每步后短等对话。"""
    try_close_popups(page)
    _neutralize_overlays_on_icon(page)

    if _click_icon(page, force=False):
        if _wait_dialog_open(page, 2_000):
            return

    if _click_icon(page, force=True):
        if _wait_dialog_open(page, 3_000):
            return

    if _click_icon_via_js(page):
        if _wait_dialog_open(page, 2_000):
            return

    if _click_icon_at_point(page):
        if _wait_dialog_open(page, DIALOG_AFTER_CLICK_MS):
            return


def wait_icon_and_open_widget(
    page: Page,
    shop_url: str,
    shop_id: str,
    *,
    icon_wait_ms: int = ICON_WAIT_MS,
    click_ms: int = ICON_CLICK_MS,
) -> None:
    """被动等到图标可见，再低频重试点击（每 3s 一整轮多策略）直至对话打开或超时。"""
    icon = _icon_locator(page)
    try:
        expect(icon).to_be_visible(timeout=icon_wait_ms)
    except Exception:
        match_count = page.locator(ICON).count()
        _fail_brief(
            page,
            f"未找到 Seel 图标（选择器 {ICON!r}，匹配 {match_count} 个）",
            shop_url=shop_url,
            shop_id=shop_id,
        )

    deadline = time.monotonic() + click_ms / 1000
    while time.monotonic() < deadline:
        if _is_dialog_open(page):
            return

        _attempt_open_widget_click(page)
        if _is_dialog_open(page):
            return

        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            break
        page.wait_for_timeout(min(CLICK_RETRY_INTERVAL_MS, remaining_ms))

    if _is_dialog_open(page):
        return

    match_count = page.locator(ICON).count()
    _fail_brief(
        page,
        f"Seel 图标已在页面上（选择器 {ICON!r} 匹配 {match_count} 个），"
        f"但 {click_ms // 1000}s 内未打开对话（{DIALOG_TITLE!r}）",
        shop_url=shop_url,
        shop_id=shop_id,
    )


def enter_if_password(page: Page, password: str, shop_id: str) -> None:
    if "/password" not in page.url:
        return
    if not password:
        _fail_brief(
            page,
            "进了密码页，但 Excel 里该行 PASSWORD 列为空",
            shop_id=shop_id,
        )
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Enter").click()
    deadline = time.monotonic() + 30.0
    while "/password" in page.url:
        if time.monotonic() > deadline:
            _fail_brief(
                page,
                "密码页：点 Enter 后 30s 内 URL 仍含 /password",
                shop_id=shop_id,
            )
        page.wait_for_timeout(200)


@pytest.mark.parametrize(
    "shop_url,password,shop_id",
    SHOPS,
    ids=[
        sid if sid else urlparse(url).netloc
        for url, _, sid in SHOPS
    ],
)
def test_live_widget(page: Page, shop_url: str, password: str, shop_id: str) -> None:
    title = shop_id or urlparse(shop_url).netloc
    allure.dynamic.title(f"Seel widget — {title}")
    # commit：收到响应、导航提交后即返回，不等待 DOMContentLoaded（部分店极慢但 widget 已注入）
    page.goto(shop_url, wait_until="commit", timeout=60_000)
    enter_if_password(page, password, shop_id)
    settle_after_goto(page)

    page.wait_for_timeout(600)
    try_close_popups(page)

    wait_icon_and_open_widget(page, shop_url, shop_id)
    page.wait_for_timeout(3_000)
    allure.attach(
        page.screenshot(full_page=False),
        name="Widget已打开",
        attachment_type=allure.attachment_type.PNG,
    )
