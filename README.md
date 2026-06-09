# Seel 店铺图标 UI 自动化（Playwright + pytest）

## 环境

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## 测试数据（Excel）

在项目根目录放置 **`live_widget登陆店铺.xlsx`**：

- 第 1 行：表头，须包含列名 **`URL`**、**`PASSWORD`**（不区分大小写、首尾空格会去掉）；两列可在任意位置，便于你在表中加其它列
- 可选列 **`STATUS`**：若表头中有该列，则**仅 `STATUS` 为 `0` 的行**会生成用例（其它数字或非数字视为不跑）；无此列时行为与以前相同，所有非空 URL 行都会跑
- 从第 2 行起：按表头 **`URL`** 读店铺地址，按 **`PASSWORD`** 读密码店前台密码（无密码店可留空）
- 其余列忽略；每一行会生成一条用例

若主题弹出广告/订阅窗遮挡点击，用例会先 **连按 Esc**、再尝试点常见 **Close** 按钮；仍失败会对图标使用 **`force` 点击** 作为兜底。个别主题可在 `tests/test_seel_support_icon.py` 的 `try_close_popups` 里补充关闭按钮选择器。

仓库里附带了一份示例表，可按行增删店铺。

## 运行

**默认无头（headless）**：不打开真实 Chrome 窗口，适合本机批量跑和 CI。pytest-playwright 在未加 `--headed` 时即为无头。

```bash
pytest
```

需要**看着浏览器**调试时，加上 `--headed` 即可（可与其它参数一起用）：

```bash
pytest --headed
```

放慢操作便于观察（有头/无头均可）：

```bash
pytest --slowmo 500
pytest --headed --slowmo 500
```

若不想使用 `pytest.ini` 里默认的 Allure 输出目录，可临时清空 addopts：

```bash
pytest -o addopts=
```

## Allure 报告与截图

- 依赖里已包含 **`allure-pytest`**；默认会在项目根目录生成 **`allure-results/`**（见 `pytest.ini` 的 `--alluredir`）。
- **成功**：对话标题「Live Support」出现后，会往 Allure 附加一张 **`Widget已打开`** 视口截图。
- **失败**：在 `tests/conftest.py` 里用钩子附加 **`用例失败截图`**（当前视口；若已无 `page` 则不会附加）。

跑完测试后生成/打开 HTML 报告需要本机安装 [Allure Commandline](https://github.com/allure-framework/allure2/releases)，例如：

```bash
pytest
allure serve allure-results
```

默认已在 `pytest.ini` 里带上 `--alluredir=allure-results`，一般无需再写。
