# Codex PE Rescue

[English](README.en.md)

**旧 Windows 已无法启动，只通过 PE 救出了 `.codex` 文件夹，重装后项目目录又换了位置？** 本项目提供从原始离线备份中选择项目和聊天、映射新路径、预览合并以及恢复的工具，同时提供一个引导操作的 Codex Skill。

不需要在旧系统上预先导出迁移包。实际项目源文件仍需自行备份和还原；聊天记录不会替代代码文件。

## 推荐：把链接交给 AI

**不用先安装 Skill，也不用安装 Git。** 将下面这段话和仓库链接发给具备本机文件读写、命令执行能力的 AI：

> 请阅读 https://github.com/E3lct/codex-pe-rescue，按其中的 AI 恢复指引帮我恢复旧 Codex 项目和聊天。先检查备份并展示恢复方案；备份位置、聊天选择或新旧项目路径无法判断时再问我。不要覆盖新聊天或上传我的数据。

AI 应先阅读 [恢复指引](skills/codex-pe-rescue/SKILL.md) 和 [操作流程](skills/codex-pe-rescue/references/assistant-workflow.md)，自行准备 [辅助脚本](skills/codex-pe-rescue/scripts/assist.py)。脚本自动获取固定版本的恢复引擎、校验文件，准备独立依赖环境并生成预览与双击启动文件。用户无需填写内部 ID、JSON 或数据库内容。

通常只需确认旧备份在哪里、恢复哪些聊天、项目现在放在哪里；AI 能从文件确认的就不重复询问。最后双击生成的启动文件并退出 Codex，窗口会等待退出、恢复并保留结果，重新打开后 AI 可读取结果继续核对。

需要可用的 Python 3.11+，AI 优先使用本机或宿主自带的运行环境；缺少时再协助安装。普通网页聊天如果无法访问本机文件，只能提供指导。首次准备会下载引擎和依赖；恢复数据不会上传。下面的命令行步骤供希望手动操作的人使用。

完整的需求选项、路径确认、独立执行及免 Python 分发规划见 [引导恢复流程设计](docs/guided-recovery-flow.md)。当前还没有自带运行环境的 EXE；不同用户的路径是输入参数，无需修改代码或重新编译。

**状态：实验性 v0.1，Windows 写入适配器。** 此版本依赖未公开稳定的本地数据库结构，不是 OpenAI 官方导入工具，也不保证兼容所有 Codex 版本。仅有历史 JSON 项目登记、没有下列数据库表的备份暂不支持。不要为了通过检查手工改数据库版本号。

## 做什么

- 从离线 `.codex` 的副本读取数据库，包括复制出来的 SQLite WAL；原备份不直接用 SQLite 打开。
- 列出项目、根目录和聊天标题，通过明确选择恢复需要的内容。
- 在独立工作目录生成预览，合并到当前已有记录，保留当前账号配置。
- 映射项目根目录、聊天运行目录和结构化运行上下文；保留聊天正文中的历史路径文字。
- 处理普通或 Zstandard 压缩的会话文件、分段依赖和历史字节偏移。
- 写入前检查客户端进程和目标变化，创建备份；写入异常时在客户端仍关闭的条件下尝试回滚。

**不处理：** ChatGPT 云端项目、账号登录迁移、项目代码拷贝、自动安装旧技能/插件、图片及外部附件二进制、不同数据库版本之间的升级转换、同一聊天 ID 的分歧历史合并。旧聊天里的图片可能仍无法显示。

## 支持条件

需要 Python 3.11+。正式 `apply` / `rollback` 仅在 Windows 上运行。源和目标均需要：

| 文件 | 本适配器使用的内容 |
| --- | --- |
| `state_5.sqlite` | `projects`、`project_roots`、`threads` 及相关表 |
| `thread_history_1.sqlite` | `thread_turns`、`thread_items`、`thread_history_projection_state`、`thread_realtime_items` |
| `sqlite/codex-dev.db` | 桌面聊天目录及同步状态 |
| `sessions/` | 被选聊天与所需分段的会话记录 |

源和目标各数据库的结构、迁移记录、`user_version` 必须一致。文件名相同不代表兼容，工具会继续检查；不兼容时停止。仅 `inspect` 可以在缺少后两库时查看主库。

v0.1 对受管理文件使用保守的 Windows 路径长度限制（小于 240 字符），拒绝符号链接/目录联接形式的受管理路径。请选择短的工作目录，比如 `E:\rescue-work-01`。

## 使用步骤

以下均为虚构示例路径；将其替换为你自己的位置。恢复工作目录包含私密聊天内容，**放在仓库外，不要提交到 GitHub**。

### 1. 安装并只读检查

在本项目目录打开独立 PowerShell：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[zstd]"
.\.venv\Scripts\codex-pe-rescue.exe inspect --source-home 'E:\RecoveredProfile\.codex'
```

`inspect` 的输出含项目名、聊天标题、ID、路径，应当作隐私文件处理。根据内容确认目标聊天；项目名称可能已经变化，不要只凭名称猜测。

如果新安装尚未产生数据库，请先正常启动并登录 Codex，让它创建自己的数据，再退出。不要用本工具复制旧 `auth.json` 来替代登录。

### 2. 配置选择和路径映射

复制 [examples/config.json](examples/config.json) 到仓库外编辑：

```json
{
  "source_home": "E:\\RecoveredProfile\\.codex",
  "target_home": "C:\\Users\\ExampleUser\\.codex",
  "project_ids": ["replace-with-project-id-from-inspect"],
  "thread_ids": [],
  "path_map": {
    "D:\\Projects\\sample": "E:\\Projects\\sample"
  }
}
```

`project_ids` 选择项目内的聊天，`thread_ids` 可额外选择单个聊天。至少选一项。只恢复某个聊天时清空 `project_ids`。覆盖所选项目根目录和聊天工作目录；多个映射匹配时最长的路径前缀优先。即使位置没变，也明确填写同路径映射。先把实际源代码还原到映射后的目录。

### 3. 生成预览

```powershell
.\.venv\Scripts\codex-pe-rescue.exe prepare --config 'E:\recovery-config.json' --workspace 'E:\rescue-work-01'
.\.venv\Scripts\codex-pe-rescue.exe verify --workspace 'E:\rescue-work-01'
```

查看工作目录中的 `preview.json`（数量和新路径）与 `plan.json`（具体选择）。`prepare` 不安装到当前 `.codex`。工作目录必须是新目录；准备后的输入和工具代码有校验，修改配置或工具后应重新准备。

### 4. 退出客户端后写入

保持这个独立 PowerShell 打开。完全退出 Codex/ChatGPT 桌面、Codex CLI 和使用 Codex 后台的编辑器。**不要在即将关闭的 Codex 内置终端执行写入。** 然后运行：

```powershell
.\.venv\Scripts\codex-pe-rescue.exe apply --workspace 'E:\rescue-work-01' --yes --codex-stopped
```

工具检测到相关进程会给出名称和 PID，不会杀进程，也没有绕过检测的命令行选项。`apply` 会用最新的目标数据重新合并，拒绝已存在的聊天 ID 和冲突的会话文件。完成后记录中必须是 `state: complete`，保存返回的 `receipt` 路径，再打开客户端检查。

备份在目标 `.codex\pe-rescue-backups\<时间与随机ID>` 中。跨盘传输先复制并校验，再在目标同目录替换，避免跨盘移动失败。多个文件不构成一个原子事务；断电/强制结束仍可能需要手工恢复。

### 5. 如需撤回

客户端继续保持关闭，用实际返回的回执路径：

```powershell
.\.venv\Scripts\codex-pe-rescue.exe rollback --receipt 'C:\Users\ExampleUser\.codex\pe-rescue-backups\<实际备份目录>\receipt.json' --yes --codex-stopped
```

自动撤回仅支持已完成且目标尚未改变的恢复。如果已经打开客户端、产生新聊天或变更记录，工具可能拒绝撤回，以免丢弃新数据。`rollback_incomplete` 表示需要人工检查，不能当成恢复成功。保留源备份、工作目录、回执和目标备份，不要反复覆盖重试。

## Skill

[skills/codex-pe-rescue/SKILL.md](skills/codex-pe-rescue/SKILL.md) 同时作为通过仓库链接进入的 AI 操作指引。它指导助手确认备份、定位聊天、准备路径映射、解释预览，再生成等待客户端退出的独立启动文件。

经常使用时，也可将该 Skill 文件夹复制到自己的 Codex skills 目录。此安装是可选的；辅助脚本会自动准备引擎，无需用户另行下载项目。项目不会自动安装 Skill 或修改当前客户端。

## 验证与实现说明

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试全部使用合成数据，覆盖普通/压缩会话、偏移重算、保留现有记录、原备份不变、写入中故障回滚、WAL 快照、路径冲突、校验及版本不匹配。合成测试不能证明所有真实 Codex 版本都可恢复。本仓库引擎没有在你的实时配置上自动执行。

方法与失败状态见 [docs/recovery-model.md](docs/recovery-model.md)。原始恢复思路来自一次系统损坏后的本地恢复，发布版本重新参数化并使用虚构测试数据；来源、依赖与相关项目见 [PROVENANCE.md](PROVENANCE.md)。

## 隐私、贡献和许可

核心恢复引擎不主动调用网络服务；辅助脚本首次准备会从固定 GitHub 提交下载引擎并从包仓库安装依赖。本地日志、预览、备份和导出的清单都可能含私密信息，不是匿名数据。`.gitignore` 只是辅助，不能取代发布前检查。

请用合成数据报告问题，勿上传 `.codex`、数据库、聊天记录、密钥、个人目录或截图。见 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [SECURITY.md](SECURITY.md)。

本项目源码采用 [MIT](LICENSE) 许可；用户数据不因此获得任何公开授权。本项目与 OpenAI 无隶属关系，也不代表其他恢复工具的作者。
