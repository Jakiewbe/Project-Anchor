<!-- codex-rules:project=1.0.0 -->
# 项目状态约定

重要工作前、新会话接续或上下文压缩后，读取最新 .agent/GOAL.md、CURRENT.md 和 tasks.json；写入使用最新 revision，冲突时重新读取，不覆盖他人更新。
目标模板中的“待确认”不代表用户已经批准。禁止自行扩大目标或开始草案任务。
用户已明确授权的局部任务可单独登记和执行，不替用户批准项目总目标。
批准目标不等于要求生成计划；只看、只评估、只做计划时停在该阶段。
tasks.json 只通过工具箱 kit.py task 修改；`task add` 只建草案，批准用 `task approve`，已批准任务的范围变更先 `task revise` 再重新批准；不要用 `task update` 改 plan 或批准范围。PROGRESS.md 是程序生成的展示。旧 schema 1/2/3 账本写前先 `migrate`。
重要决策、任务完成、用户确认变更、重大修复后，及时通过 kit.py state 更新对应状态文件。
路线确认与执行授权分别判断；允许治理写入时当回合保存，全部只读或限定修改文件时不额外写记录。
GOAL 修改必须有用户批准；CURRENT 保持 50 行以内，描述当前阶段、任务、阻塞、下一步和 Git 检查。
先 Review 查 Bug，再检查实现是否简单稳健，完成声明必须对应验证证据。
禁止擅自创建分支或工作树、推送、覆盖用户改动。任务证据结构校验不等于实际验收。

1.5接续先读取status --brief --focus；无本轮指针不猜历史任务。验收配置checks属批准范围；command用verify run，自查先Review查Bug再检查简化，用task review记录claimed/self。task update不手填证据；完成需当前材料对应结果。本机同权限工具仍可绕过，程序记录不是身份认证。

1.5.1：CURRENT保存用--task明确关联或--no-task；交付物deliverables属于批准范围，必须纳入checks.inputs。旧schema1/2/3先显式迁移；缺失交付声明不可继续或用于依赖。命令验收与claimed/self自查分别报告，历史done不等于当前成果有效。
