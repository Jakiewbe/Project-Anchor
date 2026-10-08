<!-- codex-rules:project=1.0.0 -->
# 项目状态约定

重要工作前读取 .agent/GOAL.md、CURRENT.md 和 tasks.json。
目标模板中的“待确认”不代表用户已经批准。禁止自行扩大目标或开始草案任务。
tasks.json 只通过工具箱 kit.py task 修改；PROGRESS.md 是程序生成的展示。
重要决策、任务完成、用户确认变更、重大修复后，及时通过 kit.py state 更新对应状态文件。
GOAL 修改必须有用户批准；CURRENT 保持 50 行以内，描述当前阶段、任务、阻塞、下一步和 Git 检查。
先 Review 查 Bug，再检查实现是否简单稳健，完成声明必须对应验证证据。
禁止擅自创建分支或工作树、推送、覆盖用户改动。任务证据结构校验不等于实际验收。
