# 现成方案隔离评估

日期：2026-10-08。用户补充材料提出先试用 GSD Codex 和 PMM，再判断是否继续独立扩展。本阶段保留已完成的 codex-rules 改动，停止新增功能，没有替换账本或更名。

## 验收范围

从公开来源核实仓库；源码只放入本项目 `.test-runtime/alternatives/`。测试中文和空格路径下的本地安装、既有文件保留、原生发现、进度读取、主动交接、全新会话恢复及 Git 状态。上下文压缩与规则遵从不能由文档或单元测试代替。

未把第三方方案装入用户级 Skill 目录，没有开启并行代理、创建新分支/worktree、提交或推送主项目。

## 来源和版本

“GSD Codex”存在多个同名分支，材料未保留具体链接。按最贴近其 `$gsd-*` 描述的 [Oisinwang/get-shit-done-codex](https://github.com/Oisinwang/get-shit-done-codex) 评估，不代表其他 GSD 分支。

本机下载的版本为 1.37.3，固定源码提交 `b9317ff784e8eab69789f56982fc033a60224a4e`，MIT License。原样保留上游源码，没有修改其业务逻辑或 Hook。

PMM 对应 [Jericho-Y/project-memory-manager](https://github.com/Jericho-Y/project-memory-manager)。网页检索返回的快照描述 v0.5.1，但本机 `git clone` 返回 Repository not found，GitHub API 与原始 SKILL.md 均 HTTP 404。用户随后确认“这个没了”，因此结束试装，不再等待该来源。不能仅凭 404 判断后台原因，也不能把缓存资料当成当前可安装源码；PMM 实际运行仍为 UNVERIFIED。

## GSD 本机结果

| 检查层 | 结果 | 限制 |
| --- | --- | --- |
| 中文/空格路径本地安装、重复安装 | PASS | 采用 --codex --local --no-sdk；不是默认全局安装 |
| 既有 AGENTS.md、无关 Skill 保留 | PASS | 使用已知测试原文与无关 Skill 核对 |
| 原生 Skill 发现 | PASS | skills/list 发现 81 个 gsd Skill，包括 progress/pause/resume |
| 上游聚焦自动测试 | 通过 151，失败 0 | state、health、Windows、pause、progress；包含文档结构检查，不是全部端到端 |
| SDK 本地依赖安装及编译 | PASS | 锁定依赖，仅本地安装；不执行全局 npm 安装 |
| SDK 实际查询 | 通过 2，失败 0 | init.progress、init.resume |
| 实际模型工作流 | 通过 3，失败 0 | 真实显式调用；非自然语言自动发现保证 |
| Hook 原生发现 | FAIL | 同一项目 hooks/list 返回 0；安装日志却报告已配置 SessionStart |
| 安装隔离边界 | FAIL | 即使 --local --no-sdk，也创建真实 ~/.gsd/defaults.json |
| 真正上下文压缩后的恢复 | UNVERIFIED | 主动 pause/resume 不等于自动压缩 |
| 完整研发循环与证据失效保护 | UNVERIFIED | 没有运行自动 new-project/execute/ship、并发工作区或完整阶段关闭 |

本次 GSD 演示目标是 main.py 输出 5、README 待写。模型只读进度、保存 HANDOFF.json 和 .continue-here.md，再由全新 Codex 进程读取交接并指出下一步。测试提示禁止自动提交、创建分支/worktree或继续执行开发；测试仓库仍没有提交。

第一次模型运行使用人工构造的任务背景，其中“脚本输出 5”属于夹具提供的背景；不能作为脚本独立验收。本轮复查先实际执行脚本并保存 gsd-demo-output.txt，再进行真实工作流测试，以最终结果为准。

### 安装副作用及撤销

上游 bin/install.js 的 finishInstall 无条件使用 os.homedir() 写入 `.gsd/defaults.json`，没有受 --local 约束。本次安装前审查漏查了这个结尾行为，实际新建文件只有 `resolve_model_ids: omit`，创建时间与本次安装一致。

发现后先核对内容，保存到隔离目录 gsd-unexpected-user-defaults.json，再只删除这一个本次新建文件。已确认文件不存在、该目录没有其他项目。没有删除未知文件或递归删除用户目录。此问题是实际隔离失败，不以“安装命令成功”掩盖。

默认安装还尝试全局安装 SDK。本轮明确禁用这一步，在源码 sdk/ 内按 package-lock 使用 --ignore-scripts 安装依赖，再用原 TypeScript 编译器构建；通过测试进程的 PATH 定位本地实际程序。没有全局 npm 安装或持久 PATH 修改。这是依赖的隔离安装，不是替代实现。

### Hook 与状态来源

本版本安装器将 SessionStart 写入 config.toml 的旧式 hooks 表，而当前客户端原生 hooks/list 没有发现它。该结果只证明本机版本组合下的发现失败，不代表所有旧版客户端或其他分支都失败。

GSD 使用 `.planning/PROJECT.md`、ROADMAP、STATE、PLAN/SUMMARY 和 HANDOFF；本项目使用 `.agent/tasks.json` 与受程序校验的状态。两者是不同的状态系统，不能直接同时管理同一个项目并声称已经统一。现阶段只隔离评估，没有做迁移或双向同步。

## 当前判断

已确认 GSD 的进度与主动交接流程具有可运行实现，可以研究工作流组织；本机发现的安装副作用、额外依赖和 Hook 不兼容使它尚不能直接替代当前工具箱。PMM 尚无可运行来源，不能给出优于现有实现的实测结论。

尚无证据证明必须继续扩展自己的完整执行框架，也无证据证明直接替换为 GSD/PMM 会更稳健。用户随后确认本阶段不采用 GSD，保留评估结论与现有实现，暂停外部方案引入和功能扩展。当前版本作为候选稳定基线保存；真实自动压缩恢复留待后续单独在隔离项目验证。

## 本机证据

原始文件均在 Git 忽略的 `.test-runtime/alternatives/`：

- gsd-evaluation.json、gsd-install.log、gsd-repeat.log、gsd-upstream-tests.log。
- gsd-native-list.json：真实 skills/list 与 hooks/list。
- gsd-live-result.json、gsd-live-*.jsonl：模型实际调用与最终结果。
- GSD 中文 测试项目/.planning/HANDOFF.json 和阶段 .continue-here.md。
- gsd-unexpected-user-defaults.json：已经撤销的副作用证据。

公开资料中的 Codex Agent、Codex Recall、Self-Improving Skills、Dashboard Governance、Goal Ledger 和同名插件不在本阶段试用范围；没有把其宣传说明转换为实测结论。
