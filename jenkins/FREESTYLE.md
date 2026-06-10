# Freestyle Job：pytest + Allure + PagerDuty 电话（不用 Pipeline）

和 Pipeline 能力相同：**跑测 → 失败打 PagerDuty → Jenkins 里点 Allure**。全程在网页里勾选 + 一段 shell，无需 `Jenkinsfile`。

## 0. 插件（与 Pipeline 相同）

在 **Manage Jenkins → Plugins** 安装：

| 插件 | 用途 |
|------|------|
| **Allure**（Allure Jenkins Plugin） | 构建后出「Allure Report」链接 |
| **Credentials Binding** | 把 PagerDuty Key 注入环境变量，不写死在脚本里 |

**Manage Jenkins → Tools**：配置 **Allure Commandline**（自动安装或本机路径）。

## 1. 存 PagerDuty Key（凭据）

1. **Manage Jenkins → Credentials** → **Secret text**。  
2. **Secret**：粘贴 Events API v2 的 **Integration Key**。  
3. **ID**：例如 `pd-routing-key`。  
4. 保存。

## 2. 新建 Freestyle Job

1. **New Item** → **Freestyle project** → 起名（如 `live_widget`）→ OK。  
2. **Source Code Management**：选 **Git**，填仓库 URL 与分支（与平时一样）。  
3. **Build Environment**（构建环境）：  
   - 勾选 **Use secret text(s) or file(s)**（来自 **Credentials Binding**）。  
   - **Add** → **Secret text**：**Variable** 填 `PD_ROUTING_KEY`，**Credentials** 选上一步的 `pd-routing-key`。  
4. **Build（构建）** → **Execute shell**（Linux agent；Windows 请改用「Execute Windows batch」并自行改命令）：

```bash
bash jenkins/freestyle-build.sh
```

（要求：已从 Git 检出仓库，工作目录在 workspace 根，且存在 `jenkins/freestyle-build.sh`。）

若不想调脚本，也可把 **`jenkins/freestyle-build.sh` 全文复制**到「Execute shell」里，效果一样。

5. **Post-build Actions（构建后操作）** → **Add post-build action** → **Allure Report**：  
   - **Path**：`allure-results`（与 `pytest.ini` 里 `--alluredir` 一致）。  
6. 保存 → **Build Now**。

## 3. 构建完成后去哪看

- **Allure**：进入 **该次构建** → 左侧 **Allure Report**。  
- **PagerDuty**：仅当 **`pytest` 退出码非 0** 时才会 `curl` 触发电话；成功不会打。

## 4. 可选：构建前清理 workspace

在 Job 配置里若有 **「Delete workspace before build starts」**（或 Workspace Cleanup 插件选项），按需勾选即可；与 Pipeline 里「清目录」是同一类需求。

## 5. 常见问题

| 问题 | 处理 |
|------|------|
| 没有「Use secret text」 | 安装 **Credentials Binding** 插件。 |
| 没有「Allure Report」 | 安装 **Allure** 插件，并配置 **Allure Commandline** 工具。 |
| `bash: jenkins/freestyle-build.sh: No such file` | 确认 Git 已检出且分支含该文件；或改用「整段 shell 粘贴」方式。 |
| 失败但没电话 | 检查凭据是否绑定为 **`PD_ROUTING_KEY`**（与脚本里变量名一致）；本机用同一 Key `curl` 再测一遍。 |

## 与 Pipeline 的对比

| 项目 | Freestyle | Pipeline（`Jenkinsfile.example`） |
|------|-----------|-----------------------------------|
| PagerDuty | `freestyle-build.sh` 里根据退出码 `curl` | `post { failure { curl } }` |
| Allure | Post-build Action 勾选 | `post { always { allure(...) } }` |
| 版本管理 | 脚本在 Git 里，但 Job 配置仍在 Jenkins 网页 | 可整条流水线进 Git |

两套 **都要 Allure Jenkins Plugin + Allure CLI** 才能在 Jenkins 里点开 HTML 报告。
