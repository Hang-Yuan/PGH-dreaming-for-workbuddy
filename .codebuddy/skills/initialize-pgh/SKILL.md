---
name: initialize-pgh
description: 首次打开 PGH WorkBuddy 项目时，分轮完成基础访谈、确定性写入、故事访谈、项目导入与唯一每日自动化任务验收。
user-invocable: true
---

# 初始化 PGH

## 触发

- 用户说“开始初始化 PGH”“安装 PGH”或“继续初始化”。
- `.pgh/state.json` 缺失，或状态不是 `INITIALIZED`。

## 基础阶段

1. 先运行 `python3 scripts/initialize.py --status`，不要凭记忆判断状态。
2. 若为 `UNINITIALIZED`，按 `CODEBUDDY.md §0` 分轮询问基础信息。不要一次抛出长表格，不替用户补全。
3. 形成 `.pgh/init-input.json` 预览，字段必须与 `scripts/initialize.py` 的 `REQUIRED_KEYS` 一致；把内容完整展示给用户确认。公开 `workspace/` 只作种子，个性化写入只能进入 `runtime/workspace/`。
4. 用户确认后运行：

   `python3 scripts/initialize.py --answers-file .pgh/init-input.json`

5. 回读 `python3 scripts/initialize.py --status`，必须看到 `BASIC_INITIALIZED`。失败时保留输入并报告准确错误，不宣称完成。

## 故事访谈与项目导入

- 按 `CODEBUDDY.md §0` 继续。用户可以暂停；暂停时状态保持 `BASIC_INITIALIZED`。
- 新建 USER 子文件、项目或覆盖身份层前，先展示拟写内容和加载链，取得用户确认；目标必须位于 `runtime/workspace/`。
- 不扫描用户没有指定的目录，不迁移来源不明的内容，不删除旧资料。

## 自动化任务

1. 读取 `docs/schedule_interview.md`。
2. 使用 WorkBuddy 桌面端原生自动化任务管理能力，先列出现有任务，防止重复。
3. 创建或更新唯一一条 `daily-dream`；不使用 `/loop`、操作系统计划任务或外部后台服务。
4. 保存后回读任务，核对状态、时刻、当前项目和固定提示词。
5. 只有故事访谈已确认且自动化回读成功后，运行：

   `python3 scripts/initialize.py --complete --automation-id <回读到的任务 ID>`

6. 再次回读状态，必须为 `INITIALIZED`。

## 验收

- 运行 `python3 scripts/check.py`。
- 报告基础档案、故事访谈、项目导入、hooks 审核、自动化任务和首跑证据各自状态。
- 自动化配置回读不等于首跑通过；没有计划触发历史、`COMMITTED` 收据和同日探针时，必须写“首跑待验收”。
