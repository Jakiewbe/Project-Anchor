# v1.1 Skill 验证记录

以下保留1.1.0开发验收历史；本机1.1.3已安装，已信任Hook及真实压缩的最新验收见 [PURPOSE_REVIEW.md](PURPOSE_REVIEW.md)。

日期：2026-10-08。环境：Windows 10、Python 3.11.5、Node 24.12.0、Git 2.52.0.windows.1、Codex CLI 0.162.0-alpha.2。

## 验证层次

| 层次 | 结果 | 能证明什么 |
| --- | --- | --- |
| 官方 Skill 格式校验 | PASS | SKILL.md frontmatter 有效 |
| 自动化回归 | 通过 102，失败 0 | 安装、状态校验、路径、适配器及原核心回归；不等于模型触发 |
| 原生 Hook 探针 | 通过 3，失败 0 | 发现、未信任跳过、真实 Windows 命令协议；不等于已信任生命周期 |
| 默认用户 Skill 原生发现 | PASS | 实际 ~/.agents/skills/codex-rules 被 skills/list 发现为 user，enabled=true；没有 extraRoots |
| 显式调用 | 通过 1，失败 0 | $codex-rules 实际加载和只读查询 |
| 中文自然语言正向调用 | 通过 8，失败 0 | 初始化、规划、任务完成、记忆、进度、交接、复盘、doctor；已核对真实文件和退出结果 |
| 自然语言反向调用 | 通过 5，失败 0 | 代码解释、局部脚本修改、知识问答、无关文本修改、未初始化目录的普通任务未调用本 Skill |

真实模型测试总计通过 14，失败 0。正向并非仅匹配关键词：检查实际 SKILL.md/适配器读取和状态结果；反向检查未观察到本 Skill 调用。结果是本次固定样本，不是对所有模型、措辞、配置和未来版本的保证。

## 本机证据

原始日志在被 Git 忽略的 `.test-runtime/`，不属于发布包：

- `skill-native-9ebd75ca5edb4381a971c4d2c08cd895/result.json`：显式调用。
- `skill-native-bbda98aab42147d780f71ec8813cd37f/result.json`：8 个正向、5 个反向，各自 jsonl 记录实际工具调用。
- `native-efe2d37a1e0e419a97e717534ad69269/result.json`：最终原生 Hook 探针。
- `skill-final-unittest.log`：最终完整回归。

测试临时安装到 `C:\Users\chs\.agents\skills\codex-rules`，其他规则、Hook 与清单安装到隔离 CODEX_HOME。没有复制认证、修改真实 Codex config.toml 或信任配置。测试结束按清单卸载管理文件；空目录和锁文件保留。当前不是永久用户安装。

## 安装与调用覆盖

自动化验证重复安装、旧版升级、管理文件备份、用户新增文件保留、同名非管理 Skill 拒绝覆盖、漂移拒绝、跨安装范围回滚与恢复、中文/空格路径、自定义 CODEX_HOME、不同 cwd、解释器绝对定位、shell 元字符参数、任务证据拒绝以及 Skill 缺失时独立 CLI。

Hook 直接调用原核心，不读取 Skill。真实模型触发测试关闭 Hook，便于区分 Skill 的操作与生命周期自动操作；Hook 探针单独运行。

## 已发现问题和限制

第一轮显式模型测试的执行策略禁止了实际工具调用，结果 FAIL；日志 `skill-native-f0cf495cd89649a5a9fe1a90777356d8` 保留。改用官方 `--approve-for-me` 审批路径后完成真实测试；没有禁用沙箱或绕过审批。

最终 Review 发现全局事务恢复也需要持有共享 Skill 目录锁，已补齐并增加中断恢复验证。新增测试首轮因漏导入报错，修正后的完整 102 项通过。测试失败记录保留，不用最终通过结果抹掉历史失败。

14 个真实模型样本在最后一次 Review 前执行；末轮只补充恢复锁和解释器启动说明，未改变描述、工作流、任务或状态业务逻辑。最终程序使用 102 项回归、Hook 探针及格式校验复核，没有重复消耗模型额度跑全部触发样本。

Windows 原生 home 发现不会随模拟 USERPROFILE/HOME 改变。开发隔离发现使用公开进程级 `skills/extraRoots/set`；默认用户目录另外单独实测，不能用前者冒充默认目录发现。

以下仍为 UNVERIFIED：桌面当前会话热加载、用户已信任 Hook 在完整生命周期中的执行、真实上下文压缩前后交付、模型行为长期遵从、WSL/Linux/macOS 实机集成、其他 Codex 版本。

本轮没有把 Skill 永久装入用户环境。Windows 正式安装在工具箱目录运行 `py -3 kit.py install-global`，安装后重新开启会话；日常可直接说“帮我初始化项目管理”“现在项目进度如何”“整理工作状态，准备切换会话”，也保留 `$codex-rules`。规则与 Hook 的信任审核仍按 README 执行。

本次补充材料要求先比较现成方案，因此保留已有实现和证据，停止继续扩展；比较见 ALTERNATIVES_EVALUATION.md。没有更改工具名称或替换项目账本。

## 交付文件

新增：`skills/codex-rules/SKILL.md`、`references/WORKFLOWS.md`、`references/COMMANDS.md`、`agents/openai.yaml`、`scripts/run.py`（后四项相对于 Skill 根目录）；`core/skill_install.py`、`core/native.py`；`tests/test_skill.py`、`tests/skill_native_probe.py`；本验证记录和 `docs/ALTERNATIVES_EVALUATION.md`。

修改：`kit.py`、`core/__init__.py`、`core/atomic_io.py`、`core/config.py`、`core/diagnostics.py`、`pyproject.toml`；`global/AGENTS.md`；`tests/test_kit.py`、`tests/native_probe.py`；`README.md`、`CHANGELOG.md`、`SMOKE_TEST.md`、`docs/ARCHITECTURE.md`、`docs/TROUBLESHOOTING.md`。

项目状态通过原程序更新：`.agent/GOAL.md`、CURRENT、DECISIONS、LESSONS、PROGRESS、state.json、tasks.json。第三方测试源码、日志、临时输入和验证依赖均在忽略目录；开发验收阶段没有发布、推送、创建分支/worktree或新提交。用户随后授权保存本轮候选稳定基线，准确提交号以 Git 历史为准；基线不表示长期可靠性已经全部验证。
