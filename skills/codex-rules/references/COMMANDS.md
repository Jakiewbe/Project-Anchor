# 命令与输入

安装生成本 Skill 根目录 runtime.json：python、kit、codex_home 都是绝对路径。它是执行定位信息，不是独立项目状态；不复制核心代码。先读这个文件，再运行本目录 scripts/run.py。安装后适配器可以从任何 cwd 调用，保留目标 cwd 并传入实际安装的 CODEX_HOME。

先读取 runtime.json 中 `python` 的绝对路径。PowerShell 把路径和参数作为独立参数，例如 `& $python '-X' 'utf8' $runner 'status' $project`；不要用字符串拼接后执行，也不要依赖默认 Python 或启动器。实际 Python 由适配器以参数数组启动。

| 操作 | 参数 |
| --- | --- |
| 定位检查 | --locate |
| 初始化 | init-project PATH --name NAME [--git-init] |
| 读取状态/目标/断点/任务 | status PATH |
| 明确授权重建进度 | status PATH --rebuild |
| 任务创建/更新 | task add/update PATH --file JSON --expected-revision N --reason TEXT |
| 状态更新 | state update PATH GOAL.md/CURRENT.md/DECISIONS.md/LESSONS.md --file MARKDOWN --expected-revision N --reason TEXT [--approved] |
| 检查/保存快照 | snapshot PATH [--check SNAPSHOT_FILE] |
| 诊断 | doctor PATH --json |
| 复盘 | retro PATH |
| 知识入库 | knowledge-add --file JSON --approved |

写入 task 可用 `--json-input` 代替 --file，将 UTF-8 JSON 通过 stdin 输入；state 用 `--text-input` 提交 Markdown。两者不允许与 --file 同时使用。revision 是 status 中的项目 revision，不是 task_revision。每次写入后重新读取；冲突需看新状态并重新判断，不能自动覆盖。

task add 输入：
```json
{"task_id":"T1","title":"实现接口","description":"目标内的范围","milestone":"阶段一","plan":"draft","dependencies":[],"acceptance_criteria":["实际调用成功"]}
```

task update 输入（证据必须来自实际验证）：
```json
{"task_id":"T1","status":"done","evidence":[{"type":"test","criterion":1,"detail":"真实测试命令、结果及证据位置"}]}
```

todo → doing/blocked/cancelled；doing → done/blocked/todo/cancelled；blocked → doing/todo/cancelled；done → doing；cancelled → todo。草案不能开始；doing/done 要求全部依赖 done；blocked 要求 blocker；done 证据覆盖所有标准。证据类型 test/file/review/manual/command，程序检查结构，不代替实际验收。

state update 接收完整文档。GOAL 必须有核心目标、项目背景、关键约束、非目标、验收标准、目标版本；CURRENT 必须有当前阶段、当前任务、已完成工作、当前阻塞、下一步动作、状态修订、Git 检查，50 行以内。普通更新禁止直接改原文件；外部既有编辑必须单独审核后 state adopt 登记，不用于绕过冲突。

全局安装/升级及跨电脑迁移由 install-global 统一生成定位文件和哈希；脚本移位或安装版本不同则停止并明确报告。适配器不修改 Hook 配置，移除 Skill 后 CLI 与 Hook 仍可独立执行。
