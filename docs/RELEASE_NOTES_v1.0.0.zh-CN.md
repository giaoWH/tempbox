# TempBox v1.0.0 — 发布说明

**临时文件，值得一个临时的家。**

TempBox 1.0.0 是首个面向普通用户的 macOS 版本。它是一款菜单栏工具，用来收纳那些不该长期留在桌面上的临时文件：拖入悬浮面板，设置保留期限，到期后自动移入 macOS 废纸篓。

## 下载

- 文件：`TempBox-1.0.0-macOS-arm64.dmg`
- SHA-256：`4eaa943d6b67d4017aaf156a92959a3324c7abc99a07e7dc12d5ec3ac11534db`（同时提供 `.sha256` 文件）
- 系统：macOS，Apple Silicon (arm64)，在 macOS 27.0.1 上测试
- 发布页：<https://github.com/giaoWH/tempbox/releases/tag/v1.0.0>

## 主要内容

- 紧凑菜单栏悬浮面板，支持从 Finder 拖入文件。
- 默认与单文件保留期限；到期自动进入废纸篓，启动时补做检查。
- 搜索、排序、多选、批量取回和批量修改期限。
- 自动清理暂停/恢复；暂停状态持久化，恢复积压时询问确认。
- 最近清理历史（仅元数据，最多 100 条）。
- 文件到期前 10 分钟提醒。
- Finder 快速操作 **Move to TempBox**（在设置中安装）。
- 登录启动、浅色/深色外观、单实例保护。
- 用户主动触发的 GitHub Releases 检查更新；不自动下载或安装。

## 安装

1. 从官方 GitHub Release 下载 DMG。
2. 打开 DMG，把 TempBox.app 拖入 Applications。
3. 如果 macOS 阻止首次启动，不要关闭 Gatekeeper 或 SIP。打开系统设置 → 隐私与安全性，找到 TempBox 并选择“仍要打开”；也可以在 Finder 中按住 Control 点击应用并选择“打开”。
4. 在菜单栏寻找 TempBox 图标（没有 Dock 图标）。

**未签名构建：** v1.0.0 没有 Developer ID 签名，也没有经过 Apple 公证。Gatekeeper 可能在首次启动时警告。请只从官方仓库下载，并核对 SHA-256。仅支持 Apple Silicon，不提供 Intel 构建。

## 数据与隐私

TempBox 管理的文件位于 `~/Library/Application Support/TempBox/`。到期文件移入 macOS 废纸篓，TempBox 不会永久删除。没有账号、云服务或遥测。只有用户主动检查更新时才会访问 GitHub Releases API。

## 已知限制

- 无 Developer ID 签名、Apple 公证或 Intel 构建。
- 菜单栏图标不接受 Finder 文件拖放；请使用悬浮面板。
- Quick Action 安装后可能需要重新打开 Finder，或在系统设置 → 键盘 → 键盘快捷键 → 服务中启用。
- 通知能否显示取决于 macOS 通知中心权限和未签名应用的启动方式。
- 检查更新会报告网络/API 错误；不会自动下载或安装。
- 没有自动更新或自动替换。

## 许可证

TempBox 源代码采用 Apache License 2.0。第三方组件保留各自许可证，包括 PySide6/Qt 的 LGPL-3.0 选项、Python 的 PSF 许可证、Send2Trash 的 BSD-3-Clause，以及 PyInstaller bootloader 的 GPL-2.0 + Bootloader Exception。详见 DMG 中的 `THIRD_PARTY_LICENSES.md` 和 `licenses/` 目录。

## 反馈

问题请提交至 <https://github.com/giaoWH/tempbox/issues>。请勿附带真实个人文件。
