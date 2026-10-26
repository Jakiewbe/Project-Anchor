# Project Anchor 1.4.0 验证记录

日期：2026-10-19。审查基线：`bc72aca100f5f4e5de7638b75de57085c9a1c7d0`（v1.3.0）。以下区分单元/集成测试、旧版兼容测试、安装检查和尚未完成的真实客户端行为；不把文件存在或单元测试通过等同于模型遵从。

## 范围

- 任务账本升级到 schema 2：`task add` 只建草案；`task approve` 记录批准范围；`task revise` 受控修订；`task update` 不能改 plan 或批准范围。
- 证据绑定批准版本和标准文本哈希；旧证据保留并标记失效；一次 update 不能同时改范围并完成，删除依赖不能同时开始。
- schema 1 只读与显式 `migrate`；旧任务 `legacy_unverified`，不自动补造批准记录；v1.3 读取 schema 2 拒绝。
- 新增 DeepSeek Harness `install-client dsh`、`doctor --client dsh`、卸载和恢复入口；只配置 Skill 与 `$DSH_HOME/AGENTS.md` 管理块，不配置 Hook。

## 自动化结果

命令：`py -3 -X utf8 -m unittest discover -s tests -q`。

本次运行：**193 项，192 通过、1 失败**。失败项为 `test_git_clone_preserves_hashed_state_bytes`：本机 Git for Windows 的 `sh.exe` 无法创建 signal pipe（Win32 error 5），`git clone` 返回 128。该结果保留为环境相关待核查，不宣称已经证明是环境问题；没有隔离复跑或更换 Git 配置。

专项：

| 测试 | 结果 | 覆盖 |
| --- | ---: | --- |
| `test_approval.py` | 9 / 0 | 自批、改范围、组合绕过、证据绑定、修订重批、内部字段注入 |
| `test_migration.py` | 3 / 0 | schema 1 只读、迁移标记、旧写入器拒绝、备份、重批 |
| `test_clients.py` | 26 / 0 | agents/claude/dsh 安装、漂移、卸载、doctor；DSH 规则块与 runtime |

## 迁移与旧版兼容

- 从 `bc72aca` 取旧 `kit.py` 创建 schema 1 项目，旧版创建/开始/完成任务；新版只读 `status` 通过。
- `migrate` 生成 schema 2、备份 `.agent/state.json`/`tasks.json`/`PROGRESS.md`，任务标记 `legacy_unverified`，证据补 `scope_version=0`、`criteria_hash`、`recorded_at`，不生成 `approved_scope`。
- 迁移后旧 v1.3 `status` 返回“不支持的任务账本版本”；旧 `task update` 不写入。
- legacy 任务直接 `done`/`doing` 被拒绝；先 `task revise` 再 `task approve` 后可继续。
- 重复 `migrate` 返回 `changed=false`。

## DeepSeek Harness 安装检查

在临时 `DSH_HOME` 中验证：

- `install-client dsh` 写入 `$DSH_HOME/skills/project-anchor/`、`$DSH_HOME/AGENTS.md` 管理块和 `$DSH_HOME/project-anchor/install.json`。
- `runtime.json` 为 `client=dsh`、绝对 `home`，不含 `codex_home`。
- 幂等重装 `changed=false`；用户追加的 AGENTS.md 内容在卸载后保留；SKILL.md 或规则块被人工修改时拒绝更新/卸载。
- `doctor --client dsh` 对安装清单、Skill 完整性、规则块报告 PASS；对 DSH 原生加载报告 UNVERIFIED。
- CLI `install-client dsh` / `uninstall-client dsh` / `doctor --client dsh` 可执行。

## 未完成

- 真实 DeepSeek Harness 会话中的原生 Skill 发现、显式/自动调用、`AGENTS.md` 注入、脚本权限和模型行为。
- observed 证据执行器（`verify`）、Git 冲突 `reconcile`、行为级 Agent 矩阵、状态历史归档和跨平台真实客户端验收。
- 不把本文件中的安装检查或单元测试扩大为上述能力已通过。

## 后续本地质量修复（未发布，2026-10-19）

复审后补充下列修复；原发布的 193 项测试记录保留，不能把后续结果写成原标签已经包含这些修改。

- 失效历史证据不再被当前验收条目数量限制；任务缩减标准时保留旧序号、哈希和细节，旧证据仍不能完成新范围。
- 批准与修订将完整 `approved_scope` 追加到历史，重新批准后仍可查询旧来源、原因和时间。修订也存档旧版仍存在的快照，不重写历史，不补造已丢失记录。
- 空证据数组且其他字段不变时不增加修订；非数组明确拒绝。
- 迁移预检先完整转换并校验；未知旧字段明确报错，不自动丢弃。正式迁移校验通过后才建立备份。
- DSH 诊断拒绝额外管理标记，并分别报告规则完整性、模板版本和原生加载层。

新增回归先在未修复代码上复现失败，再通过修复验证。修复后完整回归：**200 通过，0 失败**。执行环境为已获准、可正常运行 Git for Windows 克隆测试的环境；没有删除或弱化原失败测试。技能格式检查通过，检查器依赖仅放在忽略的临时目录，不改变项目依赖。

Review 后的第一性原理复核：复用现有 schema 2 历史、校验和安装机制即可，不新增账本格式或二次迁移；客户端原生行为仍需独立验收。
