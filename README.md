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
- 若使用 **`MERCHANTID`** 列：可先运行下面的同步脚本，把接口返回的 **`runMode`** 写入 **`MODE`** 列（脚本会自动创建 `MODE` 表头若不存在）

若主题弹出广告/订阅窗遮挡点击，用例会先 **连按 Esc**、再尝试点常见 **Close** 按钮；仍失败会对图标使用 **`force` 点击** 作为兜底。个别主题可在 `tests/test_seel_support_icon.py` 的 `try_close_popups` 里补充关闭按钮选择器。

仓库里附带了一份示例表，可按行增删店铺。

## 同步 widget runMode 到 Excel

表内需有 **`MERCHANTID`** 列（不区分大小写）。脚本会请求 Seel 接口 `get-connector-config`（`connectorSource=WIDGET`），把返回的 **`data.runMode`** 写回 **`MODE`** 列；若 **`MODE` 不是 `PRODUCTION`**（大小写不敏感），或该行接口失败，则把该行 **`STATUS`** 置为 **`1`**（与 pytest 里「只跑 `STATUS=0`」一致，用于跳过非生产 widget）。若无 **`STATUS`** 表头会自动追加一列。

**Jenkins**：`jenkins/freestyle-build.sh` 与 `jenkins/Jenkinsfile.example` 已在 **`pytest` 前自动执行** `python scripts/sync_widget_modes.py`（需外网、会更新仓库中的 `live_widget登陆店铺.xlsx`）。

本地可单独执行：

```bash
python scripts/sync_widget_modes.py
```

或手动先同步再跑测：

```bash
python scripts/sync_widget_modes.py && pytest
```

- 同一 `merchantId` 多行时只请求接口一次（内存缓存）。
- **`MODE` 为 `PRODUCTION`** 时**不会**改该行 `STATUS`（保留你在表里的原值）。
- 某行接口失败时，该行 **`MODE`** 会写成 `ERROR: …`（截断），**`STATUS=1`**，脚本退出码为 `1`；成功的行仍会保存。

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

- 依赖里已包含 **`allure-pytest`**；默认会在项目根目录生成 **`allure-results/`**（见 `pytest.ini` 的 `--alluredir`）。**多次运行会在该目录里累积历史结果**；本地可先删再跑：`rm -rf allure-results && pytest`。Jenkins 上 **`jenkins/freestyle-build.sh` / `Jenkinsfile.example`** 已在每次 **`pytest` 前执行 `rm -rf allure-results`**。
- **成功**：对话标题「Live Support」出现后，会往 Allure 附加一张 **`Widget已打开`** 视口截图。
- **失败**：在 `tests/conftest.py` 里用钩子附加 **`用例失败截图`**（当前视口；若已无 `page` 则不会附加）。

跑完测试后生成/打开 HTML 报告需要本机安装 [Allure Commandline](https://github.com/allure-framework/allure2/releases)，例如：

```bash
pytest
allure serve allure-results
```

默认已在 `pytest.ini` 里带上 `--alluredir=allure-results`，一般无需再写。

## Jenkins + PagerDuty + Allure

- **不想用 Pipeline**：按 **`jenkins/FREESTYLE.md`** + 脚本 **`jenkins/freestyle-build.sh`** 配置 Freestyle 即可（含失败电话 + Allure 构建后操作）。  
- **要用 Pipeline**：见 **`jenkins/Jenkinsfile.example`** 与 **`jenkins/README.md`**。
