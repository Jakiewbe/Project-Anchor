# 重要决策

## 2026-10-08：状态与写入
背景：长期状态需要可靠恢复。备选：数据库、单纯 Prompt、文件加程序。选择：标准库文件管理、OS 锁、哈希、期望修订和事务；理由：满足确定性和轻量约束。适用：本地磁盘常规项目；不自动合并多会话。

## 2026-10-08：Hook 与信任
背景：不能编造生命周期或把未审核资料提升为规则。选择：按当前官方协议配置 SessionStart/PreCompact，恢复内容需要外部精确哈希审核；原生 Hook 信任由用户在 /hooks 完成。理由：保留原生安全边界。变化：文档已明确哪些只是模拟测试。

## 2026-10-08：安装与迁移
选择：管理块加 hooks.json 清单，不重写 config.toml；原始治理状态关闭 Git 换行转换。适用：Windows 和其他本地环境分别重新安装。真实用户安装由用户执行，开发只使用隔离配置。

## 2026-10-08：原生 Skill 单入口
选择：Skill 只做意图路由，轻量适配器通过安装时记录的绝对 Python/kit/CODEX_HOME 调用原 CLI；不复制核心，不新增账本，不取代 Hooks。理由：用户无需记忆命令，确定性校验继续由 Python 完成。用户默认 Skill 目录与 CODEX_HOME 分开，跨范围写入与恢复共享锁、清单、备份和事务。

## 2026-10-08：先验证现成方案
用户补充材料转向复用评估；保留已完成 v1.1，停止新增功能，不更名或迁移账本。GSD 选用资料最贴近的 Oisinwang 分支，源码与测试都放入隔离目录；当前安装边界和 Hook 发现存在实测失败，尚不替换原系统。PMM 下载返回 404，用户确认“这个没了”，结束该项试装。真正上下文压缩与长期行为仍无验收证据。

## 2026-10-08：候选稳定基线与开发边界
用户确认：PMM 已排除，本阶段不采用 GSD，保留评估结论；保存本轮已验证改动为 Git 候选稳定基线，停止外部方案引入和功能扩展。保留 Skill、Python、AGENTS.md 与 Hook 的当前职责。允许在现有 master 创建本地提交，不推送、不创建分支或工作树、不正式安装。
候选稳定基线只代表主要功能已通过受测范围验证，不表示所有长期可靠性问题解决。真实自动压缩未来只在隔离项目补验：压缩前保存最新状态，压缩后恢复目标/任务/决策，旧快照不得覆盖新状态，Hook 未执行应能诊断发现；本轮不开展该测试。

## 2026-10-09：本机全局部署
用户明确要求本机 Codex 配置这套规则和工具，所有项目默认接入，安装后实测。按首次进入明确项目开展实际工作时接入；不扫描批量覆盖既有目录。保留目标批准、Git 提交、跨项目知识入库及原生 Hook 审核边界。全局规则负责默认接入，Skill 复用 Python 工作流；未审核摘要仍通过程序读取磁盘资料，不自动扩大内容信任。真实 Hook 信任由用户审核当前定义，不由安装程序代签。

## 2026-10-09：六项初衷复核和Hook日常使用
坚持定位为agent工具使用优化：复用既有程序，不新增平台。1.1.2将主目录/磁盘根目录排除落实到程序，Skill诊断增加只读原生审核查询。117回归、1新增真实诊断通过。官方审核界面可操作，但两项Hook仍未信任，待用户对当前定义授权后才通过原生入口启用；不写信任数据库。CLI自动新增显示检测设置已按原配置完整哈希精确撤回，不当作安全降级。真实自动压缩验收仍未完成。

## 2026-10-09：原生Hook启用授权
用户回复OK，批准通过官方入口启用前述SessionStart和PreCompact两项当前定义，并继续隔离项目压缩恢复实测。启用前已重新核对两项原生定义哈希一致；不启用其他Hook，不写信任数据库，不使用绕过信任参数。

- 2026-10-09：用户OK授权后仅通过官方审核启用既定SessionStart/PreCompact，不修改模型、权限或其他Hook。1.1.3真实客户端手动/自动压缩有原生事件、前置快照和后续读取证据；当前阶段停止扩展，保留默认项目接入、可选Skill和单一Python核心。受控阈值测试不升级为Desktop/IDE或长期保证；Git改动未提交。证据：docs/PURPOSE_REVIEW.md和.agent/runtime/deployment/lifecycle/summary.json。

- 2026-10-09：用户“改吧”授权修正JEV旧业务约束与默认接入的歧义。1.1.4明确新增治理只创建.agent并追加AGENTS/.gitignore/.gitattributes，原业务工程不重建；限制按原文范围判断，明确禁止治理或限定文件仍不接入。已拒绝操作不因规则更新自动撤销；本轮不改JEV、不改审批设置。真实正反场景均通过，证据.agent/runtime/deployment/onboarding。

- 2026-10-09：用户授权本地1.1.4提交与严格单轮验收。29个明确文件已提交b06588c，3e36159仍为祖先；不推送。测试失败保留原始现象，不在本轮修复或重复到通过。Desktop启动PASS；并发A/B按预期全部请求成功的标准为FAIL，但账本完整；残留锁C通过。JEV新接入因AGENTS只读失败并回滚，不解除只读重试。证据.agent/runtime/release-audit及临时单轮测试。

- 2026-10-09 Desktop手动压缩实测：会话01a11ebf-dbd9-7f40-81c4-9172a002962d有客户端compacted记录，PreCompact(manual)与SessionStart(compact)均PASS；快照89低于最新磁盘90，正式校验stale=true、automatic_restore=false，未覆盖新状态。恢复提供固定读取提醒，最新目标断点由status重新读盘；doctor 22 PASS、0 WARN、0 FAIL、5 UNVERIFIED。真实自动压缩、未保存聊天决定恢复和长周期仍不能据此认定可靠。证据.agent/runtime/release-audit/desktop-compaction.json及desktop-compaction-reply.json。

- 2026-10-09：用户要求补测N自然决定当回合落盘与O无背景新会话恢复。五个相同初始内容的独立合成项目已通过正式程序接入并登记目标/断点哈希；保留各自结果供O读取，不混用工具箱cwd。Desktop projectless创建接口会为已有目录生成-2副本，首次准备会话cwd错误，已停止且不计入样本。等待用户在界面添加五个已有项目后再从返回的projectId创建全新会话。P多轮衰减可选，本轮未做；不改规则/代码，不用CLI替代Desktop。证据.agent/runtime/release-audit/decision-NO。

- 2026-10-09：用户确定对外名称Project Anchor，并授权将当前项目推送至Jakiewbe/Project-Anchor、编写README。当前仅更新介绍与公开验收摘要，保留codex-rules 1.1.4的CLI、Skill、配置和运行路径；通用智能体适配是未来方向，本轮不实现。远端初始提交及MIT许可证保留，不改写已有历史。

- 2026-10-09：用户要求本机也统一Project Anchor名称，并逐步改成通用Skill，先补未验证项再推送。本轮将主Skill改为project-anchor、支持清单校验后的同父目录迁移，保留底层codex-rules存储标识以共享已有信任、日志、备份和锁；旧历史不抹除。不擅自完成其他客户端适配或原生Hook审核。

- 2026-10-09：用户授权通用Agent Skills适配并在独立分支feat/universal-agent-skills提交、推送及创建PR（不推main、不合并、不强推、不建工作树）。架构：保留唯一kit.py与.agent账本；新增install-client agents（不依赖CODEX_HOME，清单PROJECT_ANCHOR_HOME）与claude（Skill、rules/project-anchor.md、settings.json两组Hook，管理目录<配置>/project-anchor），复用所有权、备份、锁、事务和卸载。Codex Hook命令、全局规则与runtime.json字节不变，VERSION不升级。Cursor/OpenCode/WorkBuddy不写空壳适配器，持久规则依靠项目AGENTS.md，生命周期标为不支持或未验证。GOAL未修改。


## 2026-10-09：通用适配独立复核与真实安装授权边界
用户授权在现有feat/universal-agent-skills提交推送和更新Draft PR #1；未授权修改真实Codex安装、认证、Hook信任、main或历史。选择：只做隔离安装/原生查询，真实工作流使用项目级通用Skill、现有登录、Codex本次关闭Hook；不把它升级为正式安装或生命周期验收。证据：原151项独立通过，修正测试器完整响应/哈希/失败退出后155项通过；OpenCode首轮3/1保留权限拒绝，独立补做交替5/0，旧修订拒绝。Claude一次请求连续401后超时，跳过后续；不放宽权限重跑、不处理认证。文档中残留Codex专属参数已修正；现有核心与版本不变。

## 2026-10-10：通用 Skill 发布范围收口（用户批准）
用户决定不再做 Claude Code 与 WorkBuddy 的真实客户端验收，按 Agent Skills 通用规范交付同一 SKILL.md 与 scripts/run.py、唯一 kit.py 核心和 .agent 状态来源。兼容 Skill 扫描与本地 Python 执行且获得权限的 Agent 可调用；不要求每个客户端完整生命周期验收。
Hook 只在已有真实执行证据的客户端及事件范围声明可用：当前 Codex 有 install-global 与 CLI 生命周期证据；Claude 适配代码保留，不声明已验收。Cursor 3.23.12 主聊天与 OpenCode 工作流证据及限制保留。
Claude、WorkBuddy 范围外、未验证、不做、非发布阻塞；401 原始失败、未安装事实和历史 Hook 片段不改写。Codex Desktop/IDE 与仅 AGENTS.md、无 Skill 恢复对照可选、未要求，未验证层不扩大声称；不保证所有 Agent 永久遵守规则。
本轮只改文档、任务说明与状态，不改 GOAL、核心逻辑、客户端安装或任务完成状态；PR #1 保持 Draft，提交、推送及 PR 状态变更另等用户授权。依据：本轮用户批准及 docs/CLIENT_VALIDATION.md 第 10 节。
用户追加要求：README 仅保留产品定位、安装使用与能力边界，不写验收统计或历史失败；完整记录保留在验证文档。

## 2026-10-10：提交、推送与合并授权
用户要求“全部合并，推送，包括redme，PR”，授权提交本轮全部已验证文档与治理状态（包含README），推送feat/universal-agent-skills，更新PR #1标题与描述，转为可审查并合并到main；合并结果通过正式程序记录后同步远端。不创建新分支/工作树、不改写历史、不安装客户端或扩大GOAL，按现有157/0测试与证据边界发布。

## 2026-10-10：通用 Skill PR合并完成
用户授权的全部文档和治理状态（包含精简README）已通过23aeae640e1d0cbb4d7c88d2647b8567e1592761推送；PR #1标题与说明已更新、Draft已解除，并以merge提交4e77c0df115cdd9a2841cfd61bb267dc309d04cf合并main。GitHub返回merged=true、closed，本地快进后的树与受测提交完全一致；无远端CI检查项，不把空检查列表当作CI通过。
UNI1按收口后的标准和真实证据登记done；BRAND1与DPL6的旧验收状态保留，不假称历史缺口关闭。完成断点及本轮复盘通过现有分支同步远端，未创建新分支/工作树、未强推或改写历史。
