# 手动恢复指南

[English](manual-recovery.en.md) · [返回项目首页](../README.md)

本指南适用于希望自行运行命令的用户。若让具备本机文件与命令访问能力的 AI 协助，请先看仓库首页的 AI 引导说明。所有路径和 ID 都是虚构示例；恢复工作区、配置、检查输出和回执含私人数据，应放在仓库外。

## 1. 确认前置条件

**操作：**准备旧系统离线 `.codex` 文件夹的副本，并将实际项目源文件恢复到目标电脑。正常启动并登录新安装的 Codex 一次，随后退出客户端，让它创建自己的数据目录和数据库。

**预期结果：**手中有可读的旧备份、已恢复的项目目录，以及已初始化的新 Codex 目标配置目录。

**注意：**需要 Python 3.11 或更高版本；正式 `apply` 和 `rollback` 只支持 Windows。不要复制旧 `auth.json` 来登录。不要把恢复工作区放进公开仓库。工具不会恢复项目源码、账号凭据、旧技能/插件、ChatGPT 云端历史或图片/外部附件二进制。

## 2. 检查备份和兼容性

**操作：**确认将使用的 Python 版本，然后在本仓库目录打开独立 PowerShell。下方 `E:\RecoveredProfile\.codex` 是虚构备份路径。

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[zstd]"
.\.venv\Scripts\codex-pe-rescue.exe inspect --source-home 'E:\RecoveredProfile\.codex'
```

若 `python` 指向的不是 Python 3.11+，请先找到已安装的合适解释器，用其完整路径执行 `-m venv .venv`。随后统一使用本仓库的 `.venv\Scripts\python.exe`。

**预期结果：**`inspect` 列出可识别的项目、根目录、聊天标题和 ID。检查输出本身可能包含私人信息。

**注意：**项目名和聊天标题可能不同，按标题、路径和内容确认目标，不要只按名称猜。只有只读检查 `inspect` 可在缺少部分库时有限地查看主库。

写入适配器要求源和目标具备以下数据：

| 位置 | 用途 |
| --- | --- |
| `state_5.sqlite` | 项目、项目根目录、聊天及相关关系 |
| `thread_history_1.sqlite` | 聊天历史投影和实时记录 |
| `sqlite/codex-dev.db` | 桌面聊天目录和同步状态 |
| `sessions/` | 所选聊天及其依赖分段 |

源和目标数据库的结构、迁移记录和 `user_version` 必须一致。文件名一致不代表兼容；不符合时工具会停止，不要手工改数据库版本号。仅适用于原始离线配置副本，不支持用 ZIP 扩展名伪装迁移包。

## 3. 选择记录并映射路径

**操作：**复制 [`examples/config.json`](../examples/config.json) 到仓库外，再按 `inspect` 结果填写。示例中的用户目录、项目路径和 ID 均为虚构内容：

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

**预期结果：**`project_ids` 选中项目及其聊天，`thread_ids` 可额外选择单个聊天；至少选择一个项目或聊天。`path_map` 为旧项目根目录和聊天工作目录指定当前实际位置。即使目录没有移动，也要显式填写相同路径的映射。

**注意：**只恢复单个聊天时，将 `project_ids` 设为 `[]`。多个映射都匹配时使用最长的旧路径前缀。新目录必须已存在且包含实际项目文件。请勿使用推测路径。受管理路径必须短于 240 字符；符号链接或目录联接形式的受管理路径会被拒绝。

## 4. 生成并核对预览

**操作：**为本次恢复选一个仓库外的新工作目录，例如 `E:\rescue-work-01`：

```powershell
.\.venv\Scripts\codex-pe-rescue.exe prepare --config 'E:\recovery-config.json' --workspace 'E:\rescue-work-01'
.\.venv\Scripts\codex-pe-rescue.exe verify --workspace 'E:\rescue-work-01'
```

**预期结果：**工作区中生成 `preview.json` 和 `plan.json`。预览列出所选记录和路径；`verify` 返回 `"verified": true`、聊天数和会话分段数。

**注意：**工作目录必须是新目录。准备过程不会把旧记录安装到当前配置；更改配置或准备数据后，应重新准备和验证。不要向他人发送预览或配置文件。

## 5. 退出 Codex 后写入

**操作：**保持独立 PowerShell 打开，保存其他工作，并完全退出 Codex/ChatGPT 桌面、Codex CLI 及使用 Codex 后台的编辑器，再运行：

```powershell
.\.venv\Scripts\codex-pe-rescue.exe apply --workspace 'E:\rescue-work-01' --yes --codex-stopped
```

**预期结果：**成功结果为 `"state": "complete"`，并给出回执路径。目标配置目录中的备份位于 `.codex\pe-rescue-backups`。完成后重新打开 Codex，检查指定项目和聊天。

**注意：**工具检测到相关进程会显示进程名称和 PID 并拒绝写入，不会结束进程，也没有绕过检查的开关。写入前会按最新目标数据重新合并；重复聊天 ID 或冲突文件会停止。跨盘数据会复制并校验后在目标目录内替换。多个文件依次安装，不是断电原子事务。若报错，检查回执状态；`rollback_incomplete` 表示需要人工检查。保留原备份、工作区和回执，勿盲目重试。

## 6. 撤回已完成的恢复

**操作：**仅在 Codex 等客户端仍关闭、且目标自恢复后没有任何变化时，使用实际回执路径：

```powershell
.\.venv\Scripts\codex-pe-rescue.exe rollback --receipt 'C:\Users\ExampleUser\.codex\pe-rescue-backups\replace-with-actual-backup\receipt.json' --yes --codex-stopped
```

**预期结果：**成功状态为 `"state": "rolled_back"`。

**注意：**只有已完成且目标指纹未变化的恢复支持自动撤回。打开客户端、创建新聊天或改动记录后，程序会拒绝自动撤回，以免删除更新数据。不要手工改回执状态绕过保护。详见[恢复原理与失败状态](recovery-model.md)。

## 7. 测试

**操作：**在 Python 环境已安装 `.[zstd]` 的情况下运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

**预期结果：**合成数据测试通过，包含普通和压缩会话、WAL 快照、偏移重算、冲突检测、写入中断和回滚等情况。

**注意：**测试不使用真实配置，也不能证明兼容所有现有或未来的 Codex 数据库版本。测试前后均不要将个人数据放入仓库。
