# Claude Memory Manager

## Claude Code 记忆系统的不足

Claude Code 的 auto-memory 系统会为每个项目自动积累记忆文件（`~/.claude/projects/<project>/memory/`），但存在以下问题：

- **无法跨项目共享记忆**：Claude Code 原生只有 per-project 记忆，没有全局记忆机制。你在 A 项目里纠正过 Claude 的行为习惯，B 项目里它照样不知道。而 settings 有全局（`~/.claude/settings.json`）和 per-project（`.claude/settings.json`）两级结构，记忆系统理应与之同构，同样支持全局和项目两级，但 Claude Code 目前只实现了项目级。
- **记忆不透明、不可控**：记忆文件散落在 `~/.claude/` 下的多个目录里，用户看不到 Claude 记了什么，也没法统一查看、编辑或清理。

## 这个仓库做了什么

**Claude Memory Manager** 是 Claude Code 记忆系统的扩展，补全了原生缺失的全局记忆能力，并提供可视化管理界面。

**全局记忆系统**：
- 在 `~/.claude/memory/` 维护跨项目的全局记忆，与 per-project 记忆形成完整的两级结构
- 通过 Claude Code Hook 在每次会话开始时自动注入全局记忆到上下文
- 提供 Skill 让 Claude 在对话中直接增删全局记忆

**Web 管理界面**（默认 `localhost:5050`，端口冲突时自动避让）：
- 三栏布局（文件夹 / 记忆列表 / 预览编辑），统一管理全局和各项目的记忆文件
- 编辑、移动、删除记忆，支持拖拽跨容器移动
- 导出选中的记忆为 `.zip`，在另一台机器上导入

## 快速开始

```bash
claude plugin install <this-repo>
```

安装后：
- 每次 Claude Code 会话启动时，全局记忆自动注入上下文
- 管理界面自动在后台启动（默认 `http://localhost:5050`，端口冲突时自动避让，实际端口会在终端输出）

## 文件架构

```
claude-memory-manager/
├── app.py                  # Flask 薄层：HTTP 路由 → memory_ops 函数
├── memory_ops.py           # 纯函数层：所有文件系统操作（扫描/移动/删除/导出/导入/编辑）
├── templates/
│   └── index.html          # 单文件前端：三栏 UI，内联 CSS/JS，无框架，无构建步骤
├── tests/
│   ├── test_memory_ops.py  # memory_ops 单元测试
│   └── test_app.py         # Flask API 集成测试
```

运行时产生的数据目录（不在仓库内）：

```
~/.claude/memory/                          # 全局记忆容器
~/.claude/projects/<project>/memory/       # 各项目记忆容器
~/.claude-memory-manager/
└── logs/operations.jsonl                  # 所有写操作日志
```

## TODO

- [x] Web UI：查看、编辑、移动、删除、导出、导入记忆
- [x] 全局 + 各项目容器统一管理
- [x] 所有写操作可逆（日志 + 备份）
- [x] Claude Code Plugin：SessionStart Hook 自动注入记忆 + 启动 Web UI；manage-memory Skill
    - [x] SessionStart Hook：自动注入全局记忆到每次会话上下文
    - [x] Skill：在对话中让 Claude 增删全局记忆
    - [x] Session 启动时自动启动 webui

## See Also

- [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) — Claude Code 插件，自动捕获会话中 Claude 的所有操作，用 AI 压缩后在未来会话中注入相关上下文
