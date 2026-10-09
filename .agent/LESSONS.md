# 项目教训

- Windows 文本读写会转换 CRLF。外部编辑登记必须比较文字并保留原字节；BOM/CRLF 快照及克隆测试通过。证据：tests/test_kit.py；适用：UTF-8 治理文档。
- Git 自动换行会改变被哈希的状态字节。使用 .agent/** -text 保持原字节；实际本地克隆并启用 autocrlf 测试通过。
- 当前沙箱阻止 Git for Windows 创建 signal pipe；这是执行环境阻塞。放宽权限后相同本地克隆测试通过，不能用模拟结果掩盖实际失败。
- 配置识别、未信任跳过和直接运行 Windows 命令均已有实际证据；它们不能证明模型接收了恢复内容或已信任生命周期成功。

- Windows 的原生用户 Skill 发现不受模拟 USERPROFILE/HOME 控制；extraRoots 发现与默认用户目录发现必须分开验证。实际默认目录已临时安装、原生发现并按清单卸载；证据见 docs/SKILL_VALIDATION.md。
- GSD 1.37.3 的 --local --no-sdk 仍写真实 ~/.gsd/defaults.json。应审查安装末尾与辅助目录，不能仅凭 local 参数判定隔离；本次新建文件已核对、保存证据并撤销。原生 hooks/list 为 0，安装日志成功不等于 Hook 被当前客户端识别；证据见 docs/ALTERNATIVES_EVALUATION.md。
- 原生触发测试需要真实文件结果和实际工具记录；首次策略阻断记为 FAIL，允许官方审批后再测，不能用模型自述冒充通过。

- 官方信任记录hooks.state是元数据，不是内联Hook事件组；只识别实际列表事件组，非法表在写入前拒绝。120完整回归通过，正式doctor无双来源误报。
- 当前Codex原生压缩完成以item/completed的contextCompaction及成功回合核对，不能等待弃用thread/compacted；两次测试器超时保留，修正后真实手动/自动通过。证据：.agent/runtime/deployment/lifecycle。
- 新断点替代旧断点时，验收应要求新标记、固定目标/决策、真实任务状态和文件未覆盖，不要求模型再返回过期标记。手动原始断言误报保留并按此条件复核；自动新断点用例独立通过。
- PreCompact只快照已经落盘的资料；重要讨论仍须及时用Skill保存。已信任Hook在真实压缩后提示读取当前磁盘资料，旧快照存在且CURRENT更新后，手动与自动接续均读回新状态；不证明永不漂移。

- 旧指令“不要重新初始化项目”需核对原文是在保护业务工程还是禁止治理文件；不能仅用历史记忆摘要推断。1.1.4真实CLI验证保留业务仍接入、明确禁止治理则不写记录；审批说明必须覆盖.agent/AGENTS/.gitignore/.gitattributes四处。不能据此保证所有审批通过，也不能绕过已拒绝操作。
