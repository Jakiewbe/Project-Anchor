# 1.5.0 账本与上下文优化：验证记录

日期：2026-10-26（Asia/Shanghai）。环境：Windows 10 原生 PowerShell；Python 3.11.5；Git 2.52.0.windows.1；Node v24.12.0。

本轮只处理两件已批准的事：**账本体积上限**与 **`status --brief` 的任务折叠**；外加 DSH P0 结项和 CI 入口。不改 schema、不迁移既有账本、不改 `tasks.json` 历史、不剥离快照内嵌 state。

## 一、实测数字

`state.json`（本仓库自身，29 个任务、201 修订、308 条 history 的起点）：

| 项目 | 优化前 | 优化后 |
| --- | ---: | ---: |
| `state.json` | 477,105 B | 101,302 B（-79%） |
| `history` 条目 | 308 | 200（含 1 条 `history:prune`） |
| 带 `content` 的 `document-version` | 107 | 10 |
| 连续写入后的稳定性 | 每次写入线性增长 | 三次写入后仍为 101,302 B |

`status --brief`（同一账本，29 个任务，其中 23 个 `done`）：

| 调用 | 输出 | 粗估 token |
| --- | ---: | ---: |
| 优化前 `--brief` | 12,690 B | ≈3,480 |
| 优化后 `--brief` | 7,254 B | ≈2,074 |
| 优化后 `--brief --all` | 13,761 B | ≈3,766 |
| 完整 `status` | 55,847 B | ≈15,605 |

token 数为粗估（CJK ≈ 1 token/字、ASCII ≈ 4 字符/token），仅用于同口径比较。

## 二、自动验证

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 全量回归 | `py -3 -X utf8 -m unittest discover -s tests -q` | **220 通过，0 失败** |
| 新增账本/视图测试 | `py -3 -X utf8 -m unittest tests.test_history -v` | 9 通过 |
| DSH 插件测试 | `py -3 -X utf8 -m unittest tests.test_dsh_plugin -v` | 11 通过 |
| DSH 模块语法 | `node --check` × `index.js`/`tools.js`/`prompt.js`/`kit.js`/`dsh_probe.mjs` | 5/5 通过 |
| 工作流 YAML | `yaml.safe_load(.github/workflows/tests.yml)` | 解析通过 |

回归数从 211 增至 220：新增 `tests/test_history.py` 9 项。

## 三、历史裁剪的取舍

- **正文不再永久保存于 `state.json`。** 最近 10 条 `document-version` 保留全文，更早的只留 `file`、`previous_sha256`、`timestamp`、`user_approved`。Git 提交和快照仍保存完整正文；**未接入 Git 的项目**只能从快照取回旧正文。
- **裁剪按条目顺序。** `document-version` 条目没有 `revision` 字段，因此不能按修订号裁剪；`history:prune` 记录给出被丢弃条目的最小/最大 `revision`（仅统计带该字段的条目）。
- **只做一种降级顺序：先剥正文，再丢条目。** 不删除 `tasks.json` 历史，不改变证据结构。
- **上限值是模块常量**，不是每项目配置：`HISTORY_KEEP = 200`、`DOC_CONTENT_KEEP = 10`。没有新增必填字段，旧账本可直接读写。

最坏情况仍可估算：若最近 10 条都在改最大的文档（本仓库 `DECISIONS.md` 约 15 KB），`history` 正文上限约 150 KB。这是有界值，不是持续增长。

## 四、`--brief` 折叠的行为边界

- 折叠只作用于「无 `--task`、无 `--milestone`、未传 `--all`」的 brief 查询。
- `summary` 的 `total`、`statuses`、`approved_done` 口径不变；新增 `folded_final` 表示被折叠的条数，避免把「列出 6 条」误读成「只有 6 个任务」。
- 完整 `status` 与 `--brief --task ID` 行为不变，已完成任务仍返回真实状态。

## 五、DSH P0 结项证据映射

| 批准标准 | 证据 |
| --- | --- |
| `packages/dsh` 清单、patch、locale、icon 完整且静态校验 | `ManifestTests` 4 项：`test_manifest_and_patch_agree`、`test_patch_config_is_a_subset_of_the_schema`、`test_files_cover_every_runtime_module`、`test_display_resources_are_real` |
| `kit.py context PATH --json` 复用 `hook_runtime.context()`，只读，未信任项目只给指引 | `ContextCommandTests` 4 项，含 `test_untrusted_project_gets_guidance_not_content`、`test_trusted_project_injects_state_and_writes_nothing` |
| `anchor_status`/`anchor_doctor` 走真 `kit.py`，退出码即错误信号 | `HostModuleTests.test_status_tool_reads_the_real_ledger`、`test_status_tool_fails_loudly_outside_a_project` |
| `systemPrompt.section` 可注册，不改 `system-prompt/assemble` | `HostModuleTests.test_registration_and_schemas`；探针把 `systemPrompt` 包成只暴露 `section` 的 Proxy，访问 `assemble` 抛错，测试断言 `guard.assembleBlocked === true` |
| node 语法 + Python 回归全通 | `node --check` 5/5；全量回归 220 通过 |

未安装到任何 DSH profile，未取得真实会话证据；注入、guard、写工具、批准弹窗仍为设计（`docs/DSH_PLUGIN_DESIGN.md`）。P0 结项不等于 DSH 适配已验收。

## 六、GitHub Actions 实测与暴露的既有缺陷

首次推送后共跑三次（`d7d2702`、`982d131`、`f3eeb9d`），结果如下：

| run | sha | windows | linux |
| --- | --- | --- | --- |
| 40290585695 | d7d2702 | failure | success |
| 40291352004 | 982d131 | failure | success |
| 40291675312 | f3eeb9d | failure | success |

前两次的失败在**公开可读的日志之外**：job 日志需认证（403）。`tests/ci_annotate.py` 把每个失败测试写成 check-run annotation（无需 token 即可读），方才拿到真实堆栈：

```
ValueError: 'C:\Users\RUNNER~1\AppData\Local\Temp\Anchor 审批 中文 ...\项目\.agent\tasks.json'
is not in the subpath of 'C:\Users\runneradmin\AppData\Local\Temp\Anchor 审批 中文 ...\项目'
```

这是**既有缺陷，与本轮改动无关**：`core/atomic_io.py` 的 `transaction()` 用 `path.resolve()`（长路径）判断写入范围，却用未解析的短路径执行 `relative_to()`。GitHub runner 的 `TEMP` 走 8.3 短名 `RUNNER~1`，两者不一致就抛 `ValueError`；本机临时目录 `C:\\Users\\chs\\...` 本来就短，所以本地 220 项一直全绿。已在本地用 `GetShortPathNameW` 复现同一错误文本，修复为“每个更新路径只解析一次”，并新增 Windows 回归测试（不含 8.3 短名的卷自动跳过）。

## 七、未验证事项

- **修复后的 Windows CI 结果尚未确认。** 前三次均失败，修复提交需再次运行后才能声称 CI 绿。
- **Linux 仍为信息性任务。** 三次运行均通过，但 `shlex.join` 命令路径没有人工验收；`continue-on-error` 保持开启。
- **快照体积未处理。** 快照仍内嵌完整 `state`（现在因 history 有界而间接变小），没有单独裁剪逻辑。
- **`tasks.json` 历史未处理**（93 条、约 31 KB），本轮未动。
