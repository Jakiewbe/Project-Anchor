# Project Anchor · DSH bundle

DeepSeek Harness 宿主插件（P0 骨架）。它把项目治理接到 DSH 的机制上，而不是再写一份规则文本。

**唯一实现仍是 Python `kit.py`**：这个包只解析参数、启动子进程、读取 JSON 与退出码、渲染结果。任务、修订、哈希、锁、事务一条都不在这里重写。

## 当前提供（P0）

| 组件 | 作用 |
| :--- | :--- |
| `anchor_status` | 只读读取 `.agent/` 事实：项目修订、目标版本与批准状态、任务列表、断点，外加派生警告 |
| `anchor_doctor` | 只读检查安装与规则状态，`PASS/WARN/FAIL/UNVERIFIED` 分开报告 |
| `systemPrompt.section('project-anchor:governance', 700)` | 治理纪律；卸载插件即撤除，不经过 `system-prompt/assemble` |

规划中（未实现）：写工具、`.agent/` 受保护路径 guard、会话首步与压缩后注入、`/anchor` 命令、批准弹窗、状态 chip。设计见仓库 `docs/DSH_PLUGIN_DESIGN.md`。

## 安装

```
plugin_manager  action: install_bundle  target: <这个目录的绝对路径>
```

安装后确认 `application: applied`，再用 `anchor_status` 读一次真实项目；`anchor_doctor` 的 `UNVERIFIED` 行表示尚未取得的客户端证据，不要当成通过。

## 配置（`cordis.patch.yml` 的 `config`）

| 键 | 默认 | 说明 |
| :--- | :--- | :--- |
| `pythonPath` | `''` | 解释器绝对路径；留空用安装记录或 `py -3` / `python3` |
| `kitPath` | `''` | `kit.py` 文件或包含它的目录；留空读 `install-client dsh` 生成的 `runtime.json` |
| `toolTimeoutMs` | `20000` | 单次调用超时 |

## 定位顺序

1. `config.kitPath`
2. `$DSH_HOME/project-anchor/install.json` 记录的 Skill 目录 → `runtime.json`
3. `$DSH_HOME/skills/project-anchor/runtime.json`

都找不到时工具返回明确错误，插件本身不崩。

## 本地验证（无需安装 DSH）

```
py -3 -m unittest tests.test_dsh_plugin -v
```

测试用桩件加载真实的 Host 模块（`index.js`/`tools.js`/`kit.js`/`prompt.js`），校验清单与 patch 一致、schema 只用受支持子集、`apply()` 注册 2 个工具 + 1 个 section，并真的调用一次 `kit.py status`（只读断言：`state.json` 字节不变）。

## 明确未验证

- bundle 在真实 DSH profile 中安装与激活（本轮无 `plugin_manager` 工具）。
- `cordis_inspect_query` 才能确认的四项：`write`/`edit`/`bash` 的真实工具名与 `exec` 形状、审批 decision 字段、`conversation.composer.dock` 的 props、配置 schema 回读。
- 模型在真实会话中是否按 section 使用 `anchor_status`。
