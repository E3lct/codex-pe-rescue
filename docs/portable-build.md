# Windows portable build preparation

[English](portable-build.en.md) · [返回项目首页](../README.md)

本仓库准备了一份 Windows x64 单文件候选包。它把 Python 运行时、恢复助手、恢复引擎和 Zstandard 压缩支持打进一个 EXE；使用者不需要另装 Python。便携包保留和源码助手相同的命令入口，并从自己的 EXE 复制独立启动器到恢复工作区。

## 当前状态

这是构建与验证流程，不代表 GitHub 已发布下载包。当前构建未经代码签名，也未在干净 Windows 虚拟机中验证；不要把本地候选包当成正式发行版或用于真实个人数据。项目只准备 Windows x64，不提供 ARM64、32 位或其他操作系统包。

## 构建

使用 Windows x64 的 CPython 3.11+，在仓库根目录执行：

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv-build\Scripts\python.exe scripts\build_portable.py --allow-dirty
```

`requirements-build.txt` 固定 PyInstaller、压缩库、CI 工具及构建依赖。正常准备发行包时，使用干净的 Git 提交，并省略 `--allow-dirty`。脚本记录提交、工作区是否有改动、Python 与依赖版本；若构建树有未提交改动，默认会停止。

默认输出位于 `dist/`：一个候选 ZIP、ZIP 的 SHA-256 校验文件，以及内部的 EXE 校验清单、构建信息、用法说明和许可证文本。脚本不会上传或发布产物。

## 选择单文件的原因与限制

单文件便于把 EXE 复制到恢复工作区，关闭 Codex 后仍能启动。PyInstaller 运行时会把程序组件解到 Windows 临时目录，首次启动较慢；若进程被强制结束，临时目录可能残留。单文件模式也比文件夹模式更难排查，因此正式发布前仍需做干净系统测试。

候选包没有代码签名，Windows SmartScreen 或安全软件可能提示未知发布者；校验和只能确认文件未被意外改动，不能证明发布者身份或代码安全。正式发布应关联明确的提交、检查压缩包内容、生成可信构建来源证明，并在人工审核后发布不可变 Release。

## 下一步验收

- 在无系统 Python 的干净 Windows x64 环境中运行，不依赖 PATH 中的 Python 或开发工具。
- 在包含中文和空格的目录下检查、准备、验证；用合成 `.jsonl.zst` 会话验证压缩支持。
- 确认恢复工作区可将 EXE 复制为独立启动器；模拟等待超时和失败时确认目标数据不变。
- 经有授权的隔离测试环境验证客户端退出等待、完整 apply 与可回滚的合成恢复。
- 审阅发行内容、许可证、校验和和构建来源证明，再单独决定是否创建正式 Release。

恢复范围及数据限制见[项目首页](../README.md)和[手动恢复指南](manual-recovery.md)。
