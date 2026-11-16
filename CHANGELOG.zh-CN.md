# 变更记录

v1.0.0 已作为 TempBox 首个公开 macOS 版本发布。下面的版本标题对应开发阶段。

[English](CHANGELOG.md) | 简体中文

## v1.0.0 — Phase 5（已发布）

- 添加官方 Apache License 2.0、NOTICE 及第三方许可证/归属材料，包括 LGPL/GPL 文本和 Qt/PySide6 源码链接。
- 添加 PyInstaller one-directory 打包、应用图标、`TempBox.app`、未签名的 Apple Silicon DMG 及构建脚本/spec。
- 接通用户主动触发的 GitHub Releases 更新检查，支持后台 UI、版本比较，以及明确的“暂无 Release/网络/API”状态。
- 打包应用中的 Finder Quick Action helper 与登录启动改用应用路径。
- 添加未签名应用安装与 Gatekeeper 指引；本版本不含 Developer ID 签名或 Apple 公证。
- 更新文档、截图、发布元数据和版本号至 1.0.0。

## v0.5.0 — Phase 4.5（未发布）

工程整理与发布准备。

- 从 `window.py` 拆出二级窗口（自定义期限、设置、历史）到 `dialogs.py`。
- 共享显示格式化移动到 `formatting.py`；删除主题模块中重复的 `format_size`。
- 数据目录计算统一到 `paths.py`。
- 移除未使用导入和仅用于开发的原型文件。
- 截图整理到 `docs/`，完善 `.gitignore`。
- 优化外部索引刷新：只有 `records.json` 实际变化时才获取跨进程锁。
- 新增用户、开发者、贡献、变更记录文档及中文版本。
- 版本号提升到 0.5.0。

## v0.4.0 — Phase 4（未发布）

高级功能与 macOS 集成。

- Finder Quick Action **Move to TempBox**，可在设置中安装/移除，并自动刷新 macOS 服务缓存。
- 最近清理历史（仅元数据，最多 100 条，可清空）。
- 自动清理支持持久化暂停/恢复，包括启动行为和恢复积压确认。
- 文件到期前 10 分钟提醒，可关闭；多个文件合并；同一到期周期只提醒一次。
- 预留更新检查接口；设置 About 显示当前版本。
- App 与 Quick Action helper 之间的跨进程索引锁/重载，避免并发导入丢记录。
- 修复从菜单栏右键菜单退出后图标残留到下一次点击的问题。

## v0.3.5 — Phase 3.5（未发布）

- 用已确认的紧凑悬浮面板替换表格式主窗口。
- 文件行、搜索/排序、多选、批量操作、浅色/深色主题和菜单栏定位。
- 保持原有导入、取回、保留期限和清理行为。

## v0.3.0 — Phase 3（未发布）

- 搜索、排序、多选、批量取回和批量修改期限。
- 默认期限和登录启动设置。
- 失焦自动隐藏及菜单栏/托盘焦点处理。
- 更完善的状态和错误提示。

## v0.2.0 — Phase 2（未发布）

- 文件独立到期时间，到期自动移入 macOS 废纸篓。
- 保留期限预设和自定义到期时间。
- JSON schema v2（`expires_at`/`trash_error`）并兼容 version 1。
- 启动清理和清理失败重试。

## v0.1.0 — Phase 1（未发布）

- 菜单栏应用和基础文件窗口。
- 拖拽导入到 TempBox 管理存储。
- 打开、在 Finder 定位、取回文件。
- 元数据持久化和单实例锁。
