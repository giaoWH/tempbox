# 为 TempBox 贡献代码

TempBox 是一个小型 macOS 菜单栏工具。等到项目确定许可证后，欢迎提交贡献；在那之前，较大改动建议先开 issue 讨论。

[English](CONTRIBUTING.md) | 简体中文

## 开始之前

- 按 [README](README.zh-CN.md) 和 [开发指南](docs/DEVELOPMENT.zh-CN.md) 配置 macOS + Conda 环境。
- 改动前后都运行：
  ```bash
  python -m unittest discover -s tests -t . -v
  ```
- 保持改动聚焦。本项目有意避免大型框架和不必要的抽象。

## 范围与安全

- 不改变文件删除语义：过期的受管文件移入 macOS 废纸篓，绝不永久删除。
- 保持存储格式和向后兼容；已有用户数据必须能够继续加载。
- 不要使用真实用户 TempBox 数据或个人文件测试；使用临时目录和 mock 废纸篓。
- 不要实现第二套文件管理逻辑，复用 `FileStore`。
- 保持已确认的悬浮面板 UI 和视觉风格。
- 新增依赖必须有明确必要性并先讨论。

## 改动应包含

- 简明说明用户可见行为和文件安全影响。
- 针对真实数据丢失风险的测试：导入、冲突、取回、清理、JSON 持久化、暂停/恢复、历史、提醒。
- macOS 专属行为的人工验证说明（Finder、通知、菜单栏、废纸篓）。
- 行为、环境或架构变化时的文档更新。

## 风格

- Python 3.14、类型标注、优先标准库。
- 函数职责清晰，注释有意义。
- 遵循现有模块边界；不要为单个辅助函数新建小模块。
- 不要提交缓存、本地环境、日志、`.DS_Store`、构建产物或用户数据。参考 `.gitignore`。

## 许可证

TempBox 自有代码采用 **Apache License 2.0**。提交贡献即表示同意该贡献也以同一许可证分发；本项目没有单独的 CLA。第三方组件仍适用各自许可证，见 [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。

不要提交构建产物、DMG、本地环境或用户数据。
