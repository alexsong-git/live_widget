# Jenkins 接入 PagerDuty（pytest 失败电话告警）

前提：PagerDuty **Events API v2** 的 Integration Key 已在本地用 `curl` 验证能建 Incident 并打电话。

## 1. 在 Jenkins 里存 Key

1. **Manage Jenkins → Credentials**（或你 Job 所在 folder 的 Credentials）。  
2. **Add Credentials**，类型选 **Secret text**。  
3. **Secret**：粘贴 Integration Key。  
4. **ID**：例如 `pd-routing-key`（须与 `Jenkinsfile.example` 里 `credentials('pd-routing-key')` 一致）。  
5. 保存。

## 2. 方式 A：Pipeline Job（推荐）

1. **New Item** → 选 **Pipeline**，起名后保存。  
2. **Pipeline** 区域二选一：  
   - **Pipeline script from SCM**：连接 Git 仓库，`Script Path` 填 `jenkins/Jenkinsfile.example`；或  
   - **Pipeline script**：把 `Jenkinsfile.example` 全文粘贴进去，并改 `agent`、`pip` 路径、`credentials('...')` 的 ID。  
3. 保存后 **Build Now**。故意让 `pytest` 失败一次，应收到 PagerDuty 电话；成功则不应触发 `post { failure { ... } }`。

## 3. 方式 B：Freestyle Job

1. **New Item** → **Freestyle project**。  
2. **Build** → **Execute shell** 里写安装依赖 + `pytest`（与本地一致）。  
3. **构建后操作** → **Add post-build action** → 若有 **Conditional steps (single)** 或 **Post build task**：选 **Execute only if build failed**，在 shell 里写与本地验证相同的 `curl`（JSON 里 `routing_key` 不能写死）。  
4. Freestyle 默认不好注入 Secret，需装 **Credentials Binding** 相关插件，或在 **Build Environment** 勾选 **Use secret text(s) or file(s)**，把变量绑成 `PD_ROUTING_KEY`，再在失败步骤里 `$PD_ROUTING_KEY`。若插件组合复杂，优先用 **Pipeline**。

## 4. Workspace 要不要每次清理？

**不强制。** Jenkins 会复用同一 Job 的 **workspace**（路径在 `WORKSPACE` 环境变量里），`git`/SCM 检出会更新代码，多数情况不必每次清空。

| 做法 | 适用 |
|------|------|
| **不清理**（默认） | 构建快；依赖以 `pip install` 为主、可重复执行。 |
| **轻量清理**（本仓库 `Jenkinsfile.example` 里参数 **CLEAN_BUILD_ARTIFACTS**） | 怀疑 `.venv` / `allure-results` / `.pytest_cache` 脏了，勾选一次再构建。 |
| **整 workspace 清空** | 需要「接近全新 clone」时：装 **Workspace Cleanup** 插件后在 Pipeline 里 `cleanWs()`；或在 Job 的 **Git 高级行为** 里勾选 **Wipe out repository & force clone**（仅影响 SCM 目录，不等价于删整个 workspace，但常够用）。 |

全量 `cleanWs()` 会 **删掉未入库文件**，构建更慢；一般 CI 用 **按需清理** 或 **只删构建产物** 即可。

## 5. Allure 报告在 Pipeline 里怎么配？

`jenkins/Jenkinsfile.example` 已在 **`post { always { ... } }`** 里启用 **`allure([...])`**（若存在 **`allure-results/`** 目录则发布；与 `pytest.ini` 的 `--alluredir` 一致）。

### 你必须在 Jenkins 里做好的两件事（一次性）

1. **Manage Jenkins → Plugins**：安装 **Allure**（Allure Jenkins Plugin）。  
2. **Manage Jenkins → Tools**（或 Global Tool Configuration）：**Allure Commandline** 选自动安装或填本机已安装路径。

### 构建完成后去哪看

打开 **该次构建** 页面（例如 `#42`）→ 左侧 **「Allure Report」**。

### 数据从哪来

- **`pytest.ini`** 里已有 **`--alluredir=allure-results`**；Pipeline 里跑的 **`pytest`** 会在 workspace 下生成 **`allure-results/`**。  
- `allure(...)` 读取该目录生成 Jenkins 上的 HTML 入口。

若不用 Allure 插件：把 **`allure-results/`** 打成 artifact 下载后，本机执行 **`allure serve allure-results`**。

## 6. 注意

- `post { failure { sh """ ... """ } }` 必须用 **三引号双引号**，Groovy 才会展开 `${PD_ROUTING_KEY}`。  
- Agent 上需有 `curl`；无外网则无法访问 `events.pagerduty.com`。
