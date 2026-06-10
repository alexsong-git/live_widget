# Jenkins 接入 PagerDuty（pytest 失败电话告警）

前提：PagerDuty **Events API v2** 的 Integration Key 已在本地用 `curl` 验证能建 Incident 并打电话。

## 1. 在 Jenkins 里存 Key

1. **Manage Jenkins → Credentials**（或你 Job 所在 folder 的 Credentials）。  
2. **Add Credentials**，类型选 **Secret text**。  
3. **Secret**：粘贴 Integration Key。  
4. **ID**：例如 `pd-routing-key`（须与 `Jenkinsfile.example` 里 `credentials('pd-routing-key')` 一致）。  
5. 保存。

## 2. 方式 A：Freestyle（不用 Pipeline，推荐不熟 Groovy 时用）

**完整图文步骤见 [`FREESTYLE.md`](FREESTYLE.md)**。概要：

1. 安装插件：**Allure**、**Credentials Binding**；Tools 里配置 **Allure Commandline**。  
2. 凭据里存 PagerDuty **Integration Key**，ID 如 `pd-routing-key`。  
3. Freestyle Job：**Git 检出** → **Build Environment** 勾选 **Use secret text**，变量 **`PD_ROUTING_KEY`** 绑定该凭据 → **Execute shell**：`bash jenkins/freestyle-build.sh` → **Post-build Actions → Allure Report**，路径 **`allure-results`**。

脚本逻辑与 Pipeline 一致：`pytest` 失败且设置了 `PD_ROUTING_KEY` 时 `curl` 调 PagerDuty。

## 3. 方式 B：Pipeline Job

1. **New Item** → 选 **Pipeline**，起名后保存。  
2. **Pipeline** 区域二选一：  
   - **Pipeline script from SCM**：连接 Git 仓库，`Script Path` 填 `jenkins/Jenkinsfile.example`；或  
   - **Pipeline script**：把 `Jenkinsfile.example` 全文粘贴进去，并改 `agent`、`pip` 路径、`credentials('...')` 的 ID。  
3. 保存后 **Build Now**。故意让 `pytest` 失败一次，应收到 PagerDuty 电话；成功则不应触发 `post { failure { ... } }`。

不熟 Pipeline 时优先用 **§2 Freestyle + [`FREESTYLE.md`](FREESTYLE.md)**。

## 4. Workspace 要不要每次清理？

**不强制。** Jenkins 会复用同一 Job 的 **workspace**（路径在 `WORKSPACE` 环境变量里），`git`/SCM 检出会更新代码，多数情况不必每次清空。

| 做法 | 适用 |
|------|------|
| **不清理**（默认） | 构建快；依赖以 `pip install` 为主、可重复执行。 |
| **轻量清理** | 在 **Execute shell** 最前面自行加 `rm -rf .venv allure-results .pytest_cache`；或见 Freestyle 文档。 |
| **整 workspace 清空** | 需要「接近全新 clone」时：装 **Workspace Cleanup** 插件后在 Pipeline 里 `cleanWs()`；或在 Job 的 **Git 高级行为** 里勾选 **Wipe out repository & force clone**（仅影响 SCM 目录，不等价于删整个 workspace，但常够用）。 |

全量 `cleanWs()` 会 **删掉未入库文件**，构建更慢；一般 CI 用 **按需清理** 或 **只删构建产物** 即可。

## 5. Allure 报告（Pipeline 与 Freestyle）

- **Freestyle**：**Post-build Actions → Allure Report**，路径 **`allure-results`**，见 [`FREESTYLE.md`](FREESTYLE.md)。  
- **Pipeline**：`jenkins/Jenkinsfile.example` 里 **`post { always { allure(...) } }`**（若存在 `allure-results/`）。

两者都需安装 **Allure Jenkins Plugin**，并在 **Manage Jenkins → Tools** 配置 **Allure Commandline**。构建完成后：**该次构建页 → 左侧 Allure Report**。

### 你必须在 Jenkins 里做好的两件事（一次性）

1. **Manage Jenkins → Plugins**：安装 **Allure**（Allure Jenkins Plugin）。  
2. **Manage Jenkins → Tools**（或 Global Tool Configuration）：**Allure Commandline** 选自动安装或填本机已安装路径。

### 构建完成后去哪看

打开 **该次构建** 页面（例如 `#42`）→ 左侧 **「Allure Report」**。

### 数据从哪来

- **`pytest.ini`** 里已有 **`--alluredir=allure-results`**；**`pytest`** 会在 workspace 下生成 **`allure-results/`**。  
- Allure 插件读取该目录生成 Jenkins 上的 HTML 入口。

若不用 Allure 插件：把 **`allure-results/`** 打成 artifact 下载后，本机执行 **`allure serve allure-results`**。

## 6. 注意

- **Pipeline**：`post { failure { sh """ ... """ } }` 必须用 **三引号双引号**，Groovy 才会展开 `${PD_ROUTING_KEY}`。  
- **Freestyle**：用 `jenkins/freestyle-build.sh` + 环境变量 **`PD_ROUTING_KEY`**，无 Groovy。  
- Agent 上需有 `curl`；无外网则无法访问 `events.pagerduty.com`。
