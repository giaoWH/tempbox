# TempBox 使用指南

TempBox 会收纳临时文件，并在到期后把它们移入 macOS 废纸篓。它是一款菜单栏应用，主界面是紧凑的悬浮面板。

> 本文档描述已安装的 **v1.0.0** 版本（Apple Silicon）。应用通过未签名的 DMG 分发，未经 Apple 公证；首次启动可能被 Gatekeeper 阻止。安装说明见下方。开发时仍可从源码运行。

[English](USAGE.md) | 简体中文

## 安装 macOS 应用

1. 从官方 GitHub Release 下载 `TempBox-1.0.0-macOS-arm64.dmg`。
2. 打开 DMG，将 **TempBox.app** 拖入 **Applications**。
3. 如果 macOS 阻止首次启动，**不要**关闭 Gatekeeper 或 SIP。请打开 **系统设置 → 隐私与安全性**，找到 TempBox 并选择 **仍要打开**；也可以在 Finder 中按住 Control 点击应用，选择 **打开**。Apple 官方说明：<https://support.apple.com/guide/mac-help/mh40616/mac>。
4. TempBox 没有 Dock 图标；请使用菜单栏图标。

此构建没有 Developer ID 签名，也没有 Apple 公证。请只从官方 GitHub 仓库下载，并核对发布页的 SHA-256 校验值。v1.0.0 仅支持 Apple Silicon (arm64)。

## 打开面板

- 左键点击 TempBox 菜单栏图标，显示或收起面板。
- 面板显示在图标下方，自动获得焦点；点击面板外部、按 `Esc` 或 `Cmd+W` 会收起面板。
- TempBox 没有 Dock 图标。关闭/收起面板不会退出应用。
- 退出方式：面板底部的 **Quit**、`Cmd+Q`，或右键菜单栏图标选择 **Quit TempBox**。右键菜单中只有退出项。

## 添加文件

### 拖入面板

从 Finder 拖一个或多个文件到面板即可。文件会被移入 TempBox 存储，而不是复制。文件夹、符号链接和其他非普通文件会被拒绝，并在状态栏显示原因。

新文件使用当前**默认保留期限**（初始为 1 天）。

### Finder 快速操作

1. 打开设置（齿轮）→ **Install Finder Quick Action**。
2. 在 Finder 中选中一个或多个普通文件，右键。
3. 选择 **Quick Actions → Move to TempBox**；根据 macOS 版本，也可能在 **Services** 子菜单中。
4. 如果 TempBox 正在运行，文件会在约 2 秒内出现在面板中；如果未运行，Quick Action 会直接导入，下次启动时显示。

Quick Action 复用与面板完全相同的导入逻辑，并同样使用当前默认期限，不会弹出文件选择器。如果菜单项不可见：

- 重新打开 Finder 窗口，或重启 Finder；
- 同时检查右键菜单中的 **Quick Actions** 和 **Services**；
- 在系统设置 → 键盘 → 键盘快捷键 → 服务中启用 **Move to TempBox**（部分 macOS 版本位于“通用 → 登录项与扩展”）。

不需要时可在设置中移除。移动或替换 `.app` 后，请重新安装 Quick Action，使其指向新的应用路径。

> 不能把文件直接拖到菜单栏图标上。请拖入悬浮面板。

## 管理文件

文件行显示类型图标、名称、大小和相对剩余时间（如 `7 days`、`35 min`、`Expired`、`Cleanup failed`、`No expiration`）。悬停可查看加入时间和确切到期时间。

- **打开**：双击文件行，或 `···` → Open。
- **在 Finder 中定位**：`···` → Show in Finder。
- **取回**：`···` → Restore。原位置可用时直接取回；如果原路径已有同名文件或原文件夹不存在，TempBox 会让你选择目标文件夹，并且绝不会覆盖已有文件。
- **修改期限**：`···` → Change Expiration → 预设（1 小时、1 天、7 天、30 天）或 Custom…。自定义时间必须在未来。
- **搜索**：按文件名过滤。
- **排序**：Added、Name、Size、Expires。搜索和排序不会修改文件。
- **多选**：点击 **Select** 进入复选框模式，底栏出现 **Restore** 和 **Expiration** 批量操作。批量取回逐文件处理：冲突和缺失会单独报告，成功的文件仍会取回。
- **顶部**：文件数量和总大小。
- **底部**：状态、暂停提示、默认期限、History、Quit。

## 保留期限与自动清理

默认保留期限只影响**新导入**的文件，不会改变已有文件的期限。每个文件有独立的到期时间。

TempBox 运行时每 30 秒检查一次过期文件；启动时也会补做一次过期清理（除非已暂停自动清理）。过期文件会移入 macOS 废纸篓，TempBox 不会永久删除自己管理的文件。

如果移入废纸篓失败，文件和记录都会保留，文件行显示 **Cleanup failed**，稍后重试。存储文件缺失时只报告，不会当作清理成功。没有到期时间的文件（例如旧版 Phase 1 记录）永远不会被自动清理。

TempBox 未运行时不会进行清理；下次启动会处理过期文件（除非处于暂停状态）。

## 暂停与恢复自动清理

设置 → **Pause automatic cleanup**。暂停状态会持久化。

暂停期间：

- 仍可导入、打开、取回和修改期限；
- 到期时间继续正常流逝；
- 不执行任何自动过期清理，**包括启动时**；
- 面板底部显示琥珀色的 **Cleanup paused**。

恢复自动清理时，TempBox 会检查是否有已过期文件。如果有，会显示数量并询问是否立即移入废纸篓。选择 **No** 会继续保持暂停（设置也会保存为暂停），因此定时器不能绕过确认直接清理积压文件。暂停时退出并重启，仍会保持暂停。

## 最近清理历史

底部 **History** 列出最近成功清理的文件（最多 100 条）：

- 原始文件名和路径；
- 大小；
- 加入时间、到期时间和实际清理时间。

清理失败的文件不会出现在历史中；手动取回文件也不算清理事件。**Clear History** 只清空这些元数据，不会删除系统废纸篓中的任何文件。TempBox 不会自动从废纸篓恢复文件；历史仅用于帮助你定位发生过什么。

## 到期提醒

默认开启：文件距离到期不足 10 分钟时，TempBox 最多发送一次通知。多个文件同时临近到期时会合并成一条通知。修改文件期限会开启新的提醒周期。可以在设置中关闭提醒。

提醒只在 TempBox 运行时检查（启动后和周期性检查）。应用退出期间不会发送提醒。通知能否显示取决于 macOS 通知中心权限以及未签名应用的启动方式；即使通知没有显示，自动清理仍会正常执行。提醒状态仅保存在当前运行的内存中，重启后同一个到期周期可能再次提醒一次。

## 设置

齿轮按钮打开设置：

- **Default retention for new files**：只影响之后的导入；
- **Launch TempBox at login**：写入用户级 LaunchAgent，以隐藏方式启动。移动 Python 环境或项目后需要重新开关一次；
- **Pause automatic cleanup**：暂停/恢复自动清理；
- **Remind me 10 minutes before expiry**：到期提醒开关；
- **Finder Quick Action**：安装/移除 Finder 快速操作；
- **About TempBox**：当前版本和 **Check for Updates…**。只有点击时才会在后台查询官方 GitHub Releases API。

## 更新检查

**Check for Updates…** 由用户主动触发，可能显示：

- 已是最新版本；
- 发现新的稳定版本，并展示版本号、简短更新说明和 GitHub Release 链接；
- 暂无正式 Release（不会误报为“已是最新版本”）；
- 网络失败、GitHub 限流或 API 响应异常。

没有后台检查、自动下载、静默安装或自动重启。

## 文件位置

```text
~/Library/Application Support/TempBox/
├── files/<uuid>/<原始文件名>
├── records.json
├── history.json
├── settings.json
├── .instance.lock
└── .data.lock
```

元数据格式详见 [开发指南](DEVELOPMENT.zh-CN.md)。TempBox 运行期间不建议手动修改这些文件；如需操作，请先备份整个目录。

## 故障排查

- **提示应用已在运行**：同一个数据目录只允许一个 TempBox 实例；使用已运行的菜单栏图标。
- **找不到面板**：点击菜单栏图标，或重新启动应用。它不会出现在 Dock。
- **取回失败**：原文件夹可能已不存在，或存在同名文件；换一个目标文件夹。
- **Finder 快速操作不显示**：参考上文安装说明；Finder 的服务菜单缓存较顽固。
- **收不到到期提醒**：检查系统设置 → 通知中 TempBox 的权限，以及提醒开关；未签名应用的启动方式可能影响投递。
- **登录启动失效**：移动 `.app`（或从源码运行时的项目/Python 环境）后，关闭再打开登录启动设置。
