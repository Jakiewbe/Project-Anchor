# Project Anchor 1.6.0

版本：1.6.0；标签：v1.6.0。固定提交、远程 CI 与源码包校验记录在发布资产 `release-verification.json`，包哈希见 `SHA256SUMS.txt`。

## 核心变化

1. **Skill 体系底层重构（`skills/project-anchor/`）**
   - 重构 `SKILL.md`、`references/WORKFLOWS.md`、`references/COMMANDS.md`、`references/CLIENTS.md`，融合 1.5/1.5.1 规范为结构化阶段门禁、黄金主链路与故障恢复表。
   - 新增 `references/TEMPLATES.md`，提供标准 `task add`、`task review`、`GOAL.md`、`CURRENT.md`、`knowledge-add` 载荷模板及 PowerShell UTF-8 安全写入示例。
   - 强化 `scripts/run.py`：清理跨模式环境变量残留（Codex / 非 Codex 双向隔离）、缺失 `runtime.json` 时给出可操作引导，并提升版本查询容错。
2. **规则与插件版本解耦**
   - `global/AGENTS.md`、`global/CLIENT_RULES.md` 整合 schema 4 / 交付覆盖 / 双轨验收约定。
   - `packages/dsh/kit.js` 改为从 `package.json` 读取预期版本号，消除硬编码版本漂移。
3. **README 与插图重绘**
   - 重写 `README.md`，新增 `docs/assets/verification.svg`，全面重绘 `hero.svg`、`workflow.svg`、`architecture.svg` 与 4 枚状态徽章。
4. **发布与测试工程化**
   - 新增版本感知源码打包工具 `tests/prepare_release.py`（兼容旧版导入路径），补充 Skill 文档结构/模板 JSON 合法性/SVG XML/README 链接与版本一致性自动回归测试。

## 升级说明

- **schema 4 完全兼容**：1.6.0 沿用任务账本 `schema 4` 与状态格式 `schema 1`；已是 1.5.1 / schema 4 的项目无需数据迁移，在工具箱目录 `git pull --ff-only` 后重新执行原 `install-global` 或 `install-client <client>` 即可同步最新 Skill 与规则。
- **schema 1/2/3 旧项目**：升级后继续按 `status` → `migrate --dry-run` → `migrate` 流程备份迁移。
- **环境说明**：本版保持 Python 3.11+ 标准库零依赖；主验收环境为 Windows + PowerShell，Linux CI 为信息性参考；DSH 真实宿主与模型长期遵从边界保持如实标注。
