# TempBox 开发指南

本文面向从源码运行 TempBox 的开发者。用户使用说明见 [使用指南](USAGE.zh-CN.md)。

[English](DEVELOPMENT.md) | 简体中文

## 环境要求

- macOS（开发和测试环境：macOS 27.0.1，Apple Silicon）
- Conda / Miniconda
- Python 3.14（验证版本 3.14.10）
- PySide6 6.12.0
- Send2Trash 2.2.0

测试使用 Python 标准库 `unittest`，不需要额外测试框架或第三方测试依赖。

## 创建环境

推荐：

```bash
conda env create -f environment.yml
conda activate tempbox
```

如果 Conda 因 Anaconda `defaults` 频道条款未接受而报 `CondaToSNonInteractiveError`，可绕过 `defaults`：

```bash
conda create -n tempbox -c conda-forge --override-channels python=3.14 pip
conda activate tempbox
pip install PySide6==6.12.0 Send2Trash==2.2.0
```

不要提交本地环境。仓库的 `.gitignore` 已排除常见环境目录。

## 运行

```bash
cd /path/to/tempbox
conda activate tempbox
python main.py
```

`python main.py --hidden` 会只显示菜单栏图标，不打开面板（登录启动使用）。当前运行的是开发脚本而不是打包应用，因此登录启动和 Finder 快速操作会嵌入当前 Python/项目路径。

## 测试

```bash
python -m unittest discover -s tests -t . -v
```

窗口测试使用 Qt `offscreen` 平台；存储测试使用临时目录，并用 mock 替代 `send2trash`，不会触碰用户真实的 TempBox 数据。Quick Action 测试只在临时 home 目录生成 workflow，不会安装到真实的 `~/Library/Services`。

以下 macOS 行为无法可靠自动化：

- Finder 快速操作菜单注册与显示；
- 系统通知的实际可见投递；
- 菜单栏点击、焦点和视觉表现；
- 真实废纸篓操作。

这些需要人工验收；安装和排查步骤见使用指南。

## 项目结构

```text
.
├── main.py                  # 入口：python main.py
├── environment.yml          # Conda 运行环境
├── README.md                # 英文项目介绍
├── README.zh-CN.md          # 中文项目介绍
├── CONTRIBUTING.md
├── CONTRIBUTING.zh-CN.md
├── CHANGELOG.md
├── CHANGELOG.zh-CN.md
├── docs/
│   ├── USAGE.md             # 英文用户指南
│   ├── USAGE.zh-CN.md       # 中文用户指南
│   ├── DEVELOPMENT.md       # 英文开发指南
│   ├── DEVELOPMENT.zh-CN.md # 中文开发指南
│   └── screenshots/         # 正式应用截图
├── tempbox/
│   ├── app.py               # QApplication、托盘图标、菜单栏行为、退出流程
│   ├── window.py            # 悬浮面板 MainWindow 及面板逻辑
│   ├── ui_theme.py          # 主题 token、QSS、绘制图标
│   ├── ui_widgets.py        # 文件行、拖放区、空状态等面板控件
│   ├── dialogs.py           # 自定义期限、设置、清理历史窗口
│   ├── storage.py           # FileStore：导入/取回/索引/清理/跨进程锁
│   ├── history.py           # 最近清理历史（仅元数据）
│   ├── settings.py          # 持久化设置
│   ├── formatting.py        # 大小、日期、复数等显示格式化
│   ├── paths.py             # 统一数据目录
│   ├── autostart.py         # 用户级 LaunchAgent
│   ├── macos.py             # 少量 AppKit/ctypes 桥接（Dock/焦点）
│   ├── quick_action.py      # Finder Quick Action 安装器和导入 helper
│   └── updates.py           # 预留的更新检查接口
└── tests/                   # unittest 回归测试
```

模块按实际职责划分，而不是为了架构而架构：

- **UI**：`window.py`、`ui_theme.py`、`ui_widgets.py`、`dialogs.py` 只负责展示和收集用户意图，不直接移动文件。
- **核心/存储**：`storage.py` 拥有所有文件移动和索引修改；`history.py`、`settings.py` 负责各自的持久化数据。
- **系统服务**：`app.py`（菜单栏/托盘生命周期）、`quick_action.py`（Finder）、`autostart.py`（登录启动）、`macos.py`（少量原生桥接）、`updates.py`（未来更新检查）。

不要为一个简单辅助函数新建模块；只有职责明确且独立时才拆分。不要为了这个规模的应用引入框架、依赖注入或复杂抽象。

## 数据存储

数据根目录：`~/Library/Application Support/TempBox/`（见 [paths.py](../tempbox/paths.py)）。

```text
files/<uuid>/<原始文件名>     # TempBox 管理的文件；保留原始文件名
records.json                 # 索引（schema version 2）
history.json                 # 最近成功清理的元数据（最多 100 条）
settings.json                # 用户偏好
.instance.lock               # 单实例锁（QLockFile）
.data.lock                   # 跨进程索引文件锁（fcntl）
```

`records.json` 是 JSON，包含 `version: 2` 和 `files` 列表。每条记录包括：

- `id`、`original_name`、`original_path`；
- `stored_relative_path`（数据根目录下的安全相对路径）；
- `size`、`added_at`（带时区的 ISO 8601）；
- `expires_at`（UTC ISO 8601 或 null）、可选的 `trash_error`。

Phase 1 的 version 1 索引可以直接加载；缺少 `expires_at` 表示“无到期时间”，永不被自动清理。下次保存时会升级为 version 2。不要在未添加兼容处理和测试的情况下重命名字段或删除旧版支持。

`settings.json` 保存 `default_retention_seconds`、`pause_auto_cleanup` 和 `remind_before_expiry`。字段缺失时使用默认值（1 天、不暂停、开启提醒）。

`history.json` 只保存成功移入废纸篓的元数据，不保存文件内容；最多保留 100 条，最新的在前。

### 跨进程访问

App 和 Finder Quick Action helper 都可能导入文件。`FileStore` 用 `.data.lock` 上的 `fcntl.flock` 串行化读改写操作，并在检测到 `records.json` 时间戳变化时重新加载索引，避免一个进程覆盖另一个进程的记录。`MainWindow` 每 2 秒做一次轻量 `stat` 检查；只有文件确实变化时才加锁重载，因此外部导入会较快出现。

## 文件安全规则

以下规则是有意设计，不能为了简洁而削弱：

- 只清理 TempBox 存储目录内、由索引记录的文件；
- 只导入/清理普通文件（拒绝符号链接、文件夹和特殊文件）；
- 导入支持跨磁盘移动，绝不会覆盖已存储文件（每个文件使用独立 UUID 目录）；
- 取回绝不覆盖目标位置已有文件；冲突时要求重新选择文件夹；
- 清理只使用 `Send2Trash`，不会永久删除；
- 废纸篓移动失败时保留文件和索引记录以便重试；
- 存储文件缺失时报告并保留记录；
- 索引写入是原子的（临时文件 + `os.replace`）；
- 损坏索引在重建前会先备份；
- 暂停状态必须跨重启保持，不能被定时器绕过。

修改这些路径需要同步更新 `tests/test_storage.py` 和 `tests/test_window.py` 中的安全回归测试。

## Finder 快速操作

`quick_action.py` 会在 `~/Library/Services` 安装 Automator `.workflow`，并调用 `/System/Library/CoreServices/pbs -update` 让 macOS 重新读取服务列表。workflow 中的 Run Shell Script 执行：

```bash
cd "<project>" && "<python>" -m tempbox.quick_action "$@"
```

helper 会读取 `settings.json`、创建普通 `FileStore`、应用默认期限并导入选中文件，完全复用应用的安全与锁路径。App 若正在运行，会通过 2 秒一次的索引检查发现变化，不需要额外 IPC 协议。

workflow 由 `quick_action.py` 中的 plist 字典生成，已用 `/usr/bin/automator` 在临时 home 目录做过端到端验证。Finder 服务注册/缓存仍需要人工验证；排查步骤见使用指南。Phase 5 打包后需要让 workflow 指向稳定的打包应用路径，而不是当前开发 Python/项目路径。

## 通知、暂停与提醒

- `MainWindow` 负责 UI 层调度：清理每 30 秒、提醒和外部索引同步每 2 秒。
- 通知通过 `app.py` 设置的回调调用 `QSystemTrayIcon.showMessage`；通知失败被隔离，不会阻塞清理。
- 提醒状态仅存在于当前进程内存；历史和暂停状态会持久化。
- 暂停/恢复确认逻辑位于主窗口；用户取消恢复时会把暂停设置写回，后续定时器不能静默清理。

## 代码风格

- Python 3.14，使用 `from __future__ import annotations` 和标准类型标注。
- 函数职责清晰；注释只用于不直观的行为或安全规则。
- 优先标准库；不要为小任务引入新依赖。
- UI 文案简洁，与现有面板保持一致。
- 保留悬浮面板布局，不重新引入表格式主窗口。
- 修改后运行 `compileall` 和测试。
- 不要提交个人数据、日志、本地环境或构建产物。

## 参与贡献

见 [贡献指南](../CONTRIBUTING.zh-CN.md)。在公开发布前，仓库所有者需要确定许可证；当前尚未应用任何许可证。
