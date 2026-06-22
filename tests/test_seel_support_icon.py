"""Excel 驱动：进店 → 图标一出现即强行点击 → 对话窗口出现。"""

from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlparse

import allure
import openpyxl
import pytest
from playwright.sync_api import Page

ICON = ".seel_ai_support_icon"
DIALOG_TITLE = "Live Support"
ICON_WAIT_MS = 120_000
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


# 在页面脚本里查找图标（含 open shadowRoot），避免 element handle  detached
_CLICK_ICON_JS = """
() => {
  function findIcon(root) {
    const el = root.querySelector('.seel_ai_support_icon');
    if (el) return el;
    for (const node of root.querySelectorAll('*')) {
      if (node.shadowRoot) {
        const found = findIcon(node.shadowRoot);
        if (found) return found;
      }
    }
    return null;
  }
  const el = findIcon(document);
  if (!el) return false;
  el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  if (typeof el.click === 'function') el.click();
  return true;
}
"""


def settle_after_goto(page: Page) -> None:
    """commit 之后等 DOM 就绪（含自定义域名跳转），便于异步 widget 脚本执行。"""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=45_000)
    except Exception:
        pass


def _try_click_icon(page: Page) -> bool:
    """多种方式强行点击 widget 图标；每次调用都重新定位 DOM。"""
    try:
        if page.evaluate(_CLICK_ICON_JS):
            return True
    except Exception:
        pass

    try:
        icon = _icon_locator(page)
        icon.wait_for(state="visible", timeout=2_000)
        icon.scroll_into_view_if_needed(timeout=2_000)
    except Exception:
        return False

    try:
        icon.dispatch_event("click")
        return True
    except Exception:
        pass
    try:
        icon.evaluate(
            "el => { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })); el.click(); }"
        )
        return True
    except Exception:
        pass
    try:
        icon.click(force=True, timeout=2_000)
        return True
    except Exception:
        pass
    try:
        box = icon.bounding_box()
        if box and box["width"] > 0 and box["height"] > 0:
            page.mouse.click(
                box["x"] + box["width"] / 2,
                box["y"] + box["height"] / 2,
            )
            return True
    except Exception:
        pass
    return False


def wait_icon_and_open_widget(
    page: Page,
    shop_url: str,
    shop_id: str,
    *,
    timeout_ms: int = ICON_WAIT_MS,
) -> None:
    """等图标出现并点击，直到对话标题出现或超时。"""
    deadline = time.monotonic() + timeout_ms / 1000
    saw_icon = False
    while time.monotonic() < deadline:
        if page.locator(ICON).count() > 0:
            saw_icon = True
        if _try_click_icon(page):
            if _wait_dialog_open(page, DIALOG_AFTER_CLICK_MS):
                return
        page.wait_for_timeout(150)

    if _is_dialog_open(page):
        return

    if saw_icon or match_count > 0:
        _fail_brief(
            page,
            f"Seel 图标已在页面上（选择器 {ICON!r} 匹配 {match_count} 个），"
            f"但 {DIALOG_AFTER_CLICK_MS // 1000}s 内未打开对话（{DIALOG_TITLE!r}）",
            shop_url=shop_url,
            shop_id=shop_id,
        )
    _fail_brief(
        page,
        f"未找到 Seel 图标（选择器 {ICON!r}，匹配 {match_count} 个）",
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

    wait_icon_and_open_widget(page, shop_url, shop_id)
    page.wait_for_timeout(3_000)
    allure.attach(
        page.screenshot(full_page=False),
        name="Widget已打开",
        attachment_type=allure.attachment_type.PNG,
    )
