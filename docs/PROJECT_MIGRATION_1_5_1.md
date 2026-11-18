# 正式项目升级迁移记录：Project Anchor 1.5.1

日期：2026-10-30。正式版本：[v1.5.1](https://github.com/Jakiewbe/Project-Anchor/releases/tag/v1.5.1)。

本轮用户授权：将全部受本Skill影响的项目升级迁移至最新版本。执行范围为本机发现的正式项目，保留先前明确未接入的选择；历史测试、缓存和备份不作为正式项目改写。

已发现且可访问的正式项目共9个：7个从1.4.0/schema 2备份迁移至1.5.1/schema 4；OriginMaster和工具仓库原已为1.5.1/schema 4。新版Skill读取与接续入口验证9通过、0失败。FGS原路径无法访问，未验证。

## 项目结果

| 正式项目 | 实际位置 | 本轮结果 | 历史任务数 |
| --- | --- | --- | --- |
| OPEISMaster | `D:\Vibe_coding-Project\OPEISMaster` | 备份迁移至1.5.1/schema 4，更新治理规则 | 1 |
| honor-hackintosh-lab | `C:\Users\chs\.codex\.chatgpt-projects\g-p-6acbbb82add481919833bdfa4a53aaa0\honor-hackintosh-lab` | 备份迁移至1.5.1/schema 4，更新治理规则 | 4 |
| honor-hackintosh-main-g1 | `C:\Users\chs\.codex\.chatgpt-projects\g-p-6acbbb82add481919833bdfa4a53aaa0\honor-hackintosh-main-g1` | 备份迁移至1.5.1/schema 4，更新治理规则 | 5 |
| OriginMaster | `C:\Users\chs\Desktop\OriginMaster` | 原已新版；本轮更新治理规则 | 18 |
| Virtualsalpha | `D:\Vibe_coding-Project\Virtualsalpha` | 备份迁移至1.5.1/schema 4，更新治理规则 | 5 |
| DDdak | `D:\Vibe_coding-Project\DDdak` | 备份迁移至1.5.1/schema 4，更新治理规则 | 1 |
| GITTDCRmaster | `D:\Vibe_coding-Project\GITTDCRmaster` | 备份迁移至1.5.1/schema 4，更新治理规则 | 4 |
| EISMaster | `D:\Vibe_coding-Project\EISMaster` | 备份迁移至1.5.1/schema 4，更新治理规则 | 2 |
| codex-plus | `C:\Users\chs\Desktop\codex-plus` | 原已新版；核对通过 | 保留既有任务；新增本轮迁移记录 |

## 保留与核验

- 七个迁移项目原有22个任务的全部字段、状态、批准快照、证据、哈希和原历史逐项相等；只增加旧版证据标记和迁移历史。旧done保留，旧证据仍显示legacy，交付范围仍为undeclared。没有反推交付物，没有重新批准旧业务任务。
- 七个迁移项目的GOAL、CURRENT、DECISIONS、LESSONS逐字节未变；没有编造断点关联，关联状态保持unknown。
- 七个迁移项目核对7,616个业务文件的路径与SHA-256，前后一致；Git项目核对已跟踪及未忽略的未跟踪文件，非Git范围排除治理、依赖和缓存。忽略的构建产物未纳入这项哈希结论。
- 官方预检未改变受核对治理文件；正式迁移备份清单的原文件哈希全部核对；重复迁移均changed=false。
- 八个外部项目更新唯一标记后的程序管理规则段；标记前的项目自定义条款逐字节保留。原规则另有独立备份。工具仓库已有1.5.1规则，未改写。
- 所有外部Git项目的分支与HEAD前后一致；未创建分支、工作树，未提交、推送或触发业务CI。
- 九个正式项目均通过已安装Skill的status与context读取；读取前后治理文件清单与内容相同。没有项目内旧版适配器残留。全局安装清单和Skill定位文件均为1.5.1。

OriginMaster由另一个工作流持续更新，本轮发现时已经完成schema 4升级。因此本轮只更新治理规则，不写其任务、目标或断点。预检至复核期间其20个业务路径发生变化（包括新增文件），详见result.json；本轮不能将其全量业务文件宣称为未变。其当前关联changed及旧验收stale如实保留，没有补写自查或恢复绿色状态。

## 备份与证据入口

本轮本地证据：`.agent/runtime/migrate151/`，含discovery、preflight-summary、migration-summary、verification以及逐项目原规则、业务哈希、前后状态和result。此目录包含本机路径和项目资料，仅本地保留，不作为发布资产。

| 项目 | 官方治理备份 | 原治理规则备份 |
| --- | --- | --- |
| honor-hackintosh-lab | `C:\Users\chs\.codex\.chatgpt-projects\g-p-6acbbb82add481919833bdfa4a53aaa0\honor-hackintosh-lab\.agent\runtime\migrations\202610300344209878270000-866ca028b54b4d549bc155c1b4b6d542` | `C:\Users\chs\.codex\.chatgpt-projects\g-p-6acbbb82add481919833bdfa4a53aaa0\honor-hackintosh-lab\.agent\runtime\upgrades\1.5.1-20261030\AGENTS.before.md` |
| honor-hackintosh-main-g1 | `C:\Users\chs\.codex\.chatgpt-projects\g-p-6acbbb82add481919833bdfa4a53aaa0\honor-hackintosh-main-g1\.agent\runtime\migrations\202610300344224710600000-ff71acc94524452c9f042cc00fb37f35` | `C:\Users\chs\.codex\.chatgpt-projects\g-p-6acbbb82add481919833bdfa4a53aaa0\honor-hackintosh-main-g1\.agent\runtime\upgrades\1.5.1-20261030\AGENTS.before.md` |
| OriginMaster | `本轮未迁移账本` | `C:\Users\chs\Desktop\OriginMaster\.agent\runtime\upgrades\1.5.1-20261030\AGENTS.before.md` |
| DDdak | `D:\Vibe_coding-Project\DDdak\.agent\runtime\migrations\202610300344485219520000-b4aecb42d0724e52945a0839f529eab4` | `D:\Vibe_coding-Project\DDdak\.agent\runtime\upgrades\1.5.1-20261030\AGENTS.before.md` |
| EISMaster | `D:\Vibe_coding-Project\EISMaster\.agent\runtime\migrations\202610300344523694610000-3cd712805b0e48f88dbcb241b86dcdd6` | `D:\Vibe_coding-Project\EISMaster\.agent\runtime\upgrades\1.5.1-20261030\AGENTS.before.md` |
| GITTDCRmaster | `D:\Vibe_coding-Project\GITTDCRmaster\.agent\runtime\migrations\202610300344504811250000-4328228208374d4d951f033463df02d6` | `D:\Vibe_coding-Project\GITTDCRmaster\.agent\runtime\upgrades\1.5.1-20261030\AGENTS.before.md` |
| OPEISMaster | `D:\Vibe_coding-Project\OPEISMaster\.agent\runtime\migrations\202610300344197275620000-ab1ac06bf6154d9f85bddc5ea1beb2de` | `D:\Vibe_coding-Project\OPEISMaster\.agent\runtime\upgrades\1.5.1-20261030\AGENTS.before.md` |
| Virtualsalpha | `D:\Vibe_coding-Project\Virtualsalpha\.agent\runtime\migrations\202610300344466782330000-10d49c5e24ba4d2c9a9973f7c826c1ff` | `D:\Vibe_coding-Project\Virtualsalpha\.agent\runtime\upgrades\1.5.1-20261030\AGENTS.before.md` |

官方回退仅允许迁移后相关修订及文件未再变化时执行；存在后续工作时拒绝回退，不能直接覆盖备份。规则备份独立保留，不自动恢复。

## 未纳入及未验证

- JEV网申：仅有旧锁文件，无已初始化治理状态；保留用户先前明确不接入的选择，没有初始化。
- 9个历史验证副本：HONOR缓存中的4个旧测试副本、2026-10-09的5个合成测试项目，保留原样作为历史证据。
- project-template及审计源码快照中的局部.agent不属于已初始化正式项目，未迁移。
- 不可访问或已不存在的已登记路径如下；不计入通过，也不从路径名猜测其是否曾接入：
  - `C:\Users\chs\Desktop\1`
  - `C:\Users\chs\Desktop\3.29OPEIS\DRT`
  - `C:\Users\chs\Desktop\3.29OPEIS\处理`
  - `C:\Users\chs\Desktop\matlab-DRTtools`
  - `C:\Users\chs\Desktop\参考文献`
  - `C:\Users\chs\Desktop\课程文件`
  - `C:\Users\chs\Desktop\高压Small`
  - `F:\FGS-1-6`

扫描范围：应用登记的本地项目、桌面、D盘项目目录、Documents/Codex、Codex本地项目目录及既有信任登记；按真实路径去重。发现10,450个可读目录。14个缓存或临时目录拒绝访问，详见discovery.json；这些目录内部未核验。本结论不覆盖未挂载磁盘、其他用户目录或远端机器。

本轮验证的是治理格式升级、规则及接续读取，不重新运行各项目业务验收，不证明仪器、生产环境或最终图面通过。未重新验证每个项目的新会话自动触发、Hook信任或模型实际遵守。

## 自检

Review：核对原任务所有字段和历史、备份清单、业务哈希、分支HEAD及新旧规则差异；未发现迁移引入的任务丢失、业务改写或自定义规则覆盖。OriginMaster并发变化单独报告，不计作业务保留失败或本轮验收通过。

第一性原理检查：复用官方migrate和共享Skill，不复制核心、不初始化新项目、不补造deliverables/current关联。只替换明确由工具管理的规则尾段，未增加客户端专属行为。
