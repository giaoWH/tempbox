# TempBox

**临时文件，值得一个临时的家。**

TempBox 是一款轻量的 macOS 菜单栏工具，专门收纳那些不该长期堆在桌面上的临时文件。把文件拖进悬浮面板，设置保留期限，TempBox 会把它放进自己的存储目录；到期后自动移入 macOS 废纸篓。文件随时可以打开、在 Finder 中定位、取回，或重新设置到期时间。

项目当前处于 **Phase 4.5（v0.5.0）**。目前通过 Python/Conda 环境运行；正式签名的 `.app` 和公开发布计划在 Phase 5 完成。

[English](README.md) | 简体中文

![TempBox 深色面板](docs/screenshots/01-dark-three-files.png)

## 为什么是 TempBox

- **给临时文件一个真正的归宿。** 不藏在桌面，也不混进“下载”文件夹。
- **永远不会被永久删除。** 过期文件进入 macOS 废纸篓，仍可恢复。
- **默认安全。** 只处理 TempBox 自己管理、位于其存储目录内的文件。
- **操作成本低。** 紧凑面板、Finder 拖拽、批量操作和 Finder 快速操作覆盖日常使用。
- **安静、原生。** 没有 Dock 图标，没有账号、云同步或常驻后台守护进程。

## 功能

- 点击菜单栏图标打开紧凑悬浮面板。
- 从 Finder 拖入单个或多个文件。
- 默认保留期限（初始为 1 天），支持单个文件的预设期限和自定义时间。
- 到期自动移入 macOS 废纸篓；启动时补做过期检查。
- 暂停/恢复自动清理；暂停状态持久化，恢复时若有积压文件会先询问。
- 按添加时间、名称、大小、到期时间搜索和排序。
- 多选后批量取回或批量修改期限。
- 在默认应用中打开、在 Finder 中定位、取回到原位置或指定文件夹。
- 最近清理历史（仅元数据，最多 100 条），可手动清空。
- 文件到期前 10 分钟提醒（可关闭；多个文件合并提醒）。
- Finder 快速操作 **Move to TempBox**（在设置中安装）。
- 通过 LaunchAgent 登录启动。
- 跟随系统浅色/深色外观。
- 设置中提供当前版本和检查更新入口；本开发版本尚未启用联网更新检查。

更多说明：[使用指南](docs/USAGE.zh-CN.md) · [开发指南](docs/DEVELOPMENT.zh-CN.md) · [变更记录](CHANGELOG.zh-CN.md) · [贡献指南](CONTRIBUTING.zh-CN.md)。

## 环境要求

- macOS（开发和测试环境：macOS 27.0.1，Apple Silicon）
- Conda / Miniconda
- Python 3.14（验证版本 3.14.10）
- PySide6 6.12.0、Send2Trash 2.2.0

TempBox 目前是开发版本，**没有公开发布的 `.app` 安装包**。

## 从源码运行

```bash
git clone <repository-url>
cd tempbox
conda env create -f environment.yml
conda activate tempbox
python main.py
```

如果 `conda env create` 因 Anaconda `defaults` 频道条款未接受而报 `CondaToSNonInteractiveError`，请使用 [开发指南](docs/DEVELOPMENT.zh-CN.md) 中不经过 `defaults` 频道的显式安装命令。

`python main.py --hidden` 会以“仅菜单栏”方式启动（登录启动使用这个命令）。测试和项目结构见 [开发指南](docs/DEVELOPMENT.zh-CN.md)。

## 快速使用

点击菜单栏图标打开面板，把文件拖入即可，文件使用当前默认期限。文件行右侧的 `···` 菜单可以打开、定位、取回或修改期限；点击 **Select** 进入多选批量操作；齿轮按钮打开设置。

到期文件会移入 macOS 废纸篓，不会被永久删除。TempBox 未运行时，过期清理会在下次启动时进行；暂停状态在重启后仍然有效。完整说明见 [使用指南](docs/USAGE.zh-CN.md)。

### Finder 快速操作

设置 → **Install Finder Quick Action** 会在 `~/Library/Services` 中创建 `Move to TempBox.workflow`，并刷新 macOS 服务缓存。之后在 Finder 中选中文件 → 右键 → **Quick Actions**（或 **Services**）→ **Move to TempBox**。

如果菜单项没有出现：

- 重新打开 Finder 窗口，或重启 Finder；
- 同时检查右键菜单中的 **Quick Actions** 和 **Services**；
- 在系统设置 → 键盘 → 键盘快捷键 → 服务中启用 **Move to TempBox**（部分 macOS 版本位于“通用 → 登录项与扩展”）。

### 菜单栏图标拖拽

当前 PySide6 `QSystemTrayIcon` 不支持把文件直接拖到菜单栏图标上。请使用悬浮面板拖入。这是为了不引入不稳定的原生状态栏桥接而做的有意取舍。

## 文件安全

TempBox 管理的文件位于：

```text
~/Library/Application Support/TempBox/files/<uuid>/<原始文件名>
```

索引为 `records.json`，设置为 `settings.json`。清理规则：

- 只考虑 TempBox 记录中、位于 TempBox 存储目录内的文件；
- 只处理普通文件，且只处理自身到期时间已过的文件；
- 使用 `Send2Trash` 移入废纸篓，可恢复；
- 废纸篓操作失败时保留文件和记录，稍后重试；
- 文件缺失只报告，不当作清理成功；
- App 与 Finder 快速操作通过文件锁串行写入索引，避免互相覆盖。

缺失或未知的元数据绝不会被用于删除任意文件。清理历史和提醒本身不删除文件。数据格式详见 [开发指南](docs/DEVELOPMENT.zh-CN.md)。

## 截图

| 深色面板 | 浅色面板 |
| --- | --- |
| ![深色面板](docs/screenshots/01-dark-three-files.png) | ![浅色面板](docs/screenshots/02-light-three-files.png) |
| **多选批量操作** | **文件操作菜单** |
| ![多选](docs/screenshots/03-dark-selection-mode.png) | ![文件操作菜单](docs/screenshots/04-dark-file-actions-menu.png) |

## 项目状态

| 阶段 | 内容 | 版本 |
|---|---|---|
| 1 | 基础文件管理 | v0.1 |
| 2 | 保留期限与废纸篓生命周期 | v0.2 |
| 3 | 搜索、批量操作、登录启动 | v0.3 |
| 3.5 | 悬浮面板 UI 集成 | v0.3.5 |
| 4 | Finder 快速操作、历史、暂停、提醒 | v0.4 |
| 4.5 | 代码重构、项目清理、文档 | v0.5 |

**仓库中尚不包含：** 打包好的 `.app`/`.dmg`、代码签名与公证、GitHub Release、正式联网更新检查、最终应用图标。这些属于 Phase 5。

### 后续路线

- **Phase 5：** 应用图标、`.app`/`.dmg` 打包、签名与公证、GitHub Releases、联网更新检查，以及打包环境下对 Finder 快速操作注册和通知投递的验证。暂不承诺具体日期。

## 许可证

本项目尚未选择许可证。对于这样的小型工具，建议考虑 **MIT** 或 **Apache-2.0**；最终由仓库所有者决定。在确定之前，请不要默认代码已经以某种开源许可证授权。详见 [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)。
