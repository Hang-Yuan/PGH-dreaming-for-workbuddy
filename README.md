# PGH Dreaming for WorkBuddy

一个面向 WorkBuddy 的本地优先长期协作与记忆骨架。仓库只包含空白模板、项目规则、技能、hooks、初始化器和发布审计；不包含发布者身份、私人档案、真实会话、凭证、本机绝对路径或内部服务地址。

当前版本：`v6.2.2-workbuddy.1`。

## 下载后开始初始化

1. 下载 ZIP 并解压，或克隆本仓库。
2. 在 WorkBuddy 中把**仓库根目录**作为项目打开。
3. 发送：`开始初始化 PGH`。
4. WorkBuddy 会读取根目录的 `CODEBUDDY.md`，调用 `initialize-pgh`，先完成约 5 分钟的基础访谈，再继续可暂停的故事访谈。
5. WorkBuddy 首次发现项目 hooks 时会要求审核。先在 `/hooks` 面板查看脚本，再允许项目 hooks；拒绝也不会阻止基础初始化，只会停用会话身份补注。

无需把 `.codebuddy/` 复制到用户目录，也无需把 `workspace/` 移到其他位置。ZIP 下载与 Git 克隆使用同一条初始化路径。

也可以在终端启动基础访谈：

```bash
python3 scripts/initialize.py --interactive
```

## 初始化状态

初始化器保持公开 `workspace/` 不变，把它复制到已忽略的 `runtime/workspace/` 后再写入个性化内容；状态写入 `.pgh/state.json`：

| 状态 | 含义 |
|---|---|
| `UNINITIALIZED` | 尚未完成基础访谈 |
| `BASIC_INITIALIZED` | 基础档案和时间边界已写入；故事访谈或排程仍可能待完成 |
| `INITIALIZED` | 故事访谈已确认，且 WorkBuddy 原生每日自动化任务已回读验证 |

初始化器不会替用户编造内容，不会扫描任意旧目录，不会删除旧资料，也不会把初始化答案上传或写入 Git 配置。

## WorkBuddy 宿主边界

- 项目指令：`CODEBUDDY.md` 与 `.codebuddy/rules/`
- 项目技能：`.codebuddy/skills/*/SKILL.md`
- 项目子代理：`.codebuddy/agents/*.md`
- 项目 hooks：`.codebuddy/settings.json` + `.codebuddy/hooks/runtime_context.py`
- 公开空白模板：`workspace/`
- 本地现役工作空间：`runtime/workspace/`（不入库）
- 本地运行状态：`.pgh/`（不入库）
- WorkBuddy L0：由 `.codebuddy/skills/daily-dream/scripts/extract_daily_transcripts.py` 从本地项目会话中按逻辑日提取

长期每日做梦使用 **WorkBuddy 桌面端的原生自动化任务**。CodeBuddy CLI 的 `/loop` 属于会话级临时任务，退出后消失且会自动过期，不能作为持久每日排程。

## 唯一每日任务合同

- 名称：`daily-dream`
- 数量：恰好一条
- 时刻：用户确认的逻辑日界线后 30 分钟
- 项目：当前仓库根目录
- 提示：`使用 $daily-dream 处理最近一个已经闭合的逻辑日；严格执行事务闸，并报告提交收据。`
- 周级与季度级流程：由日链按目标日期条件调用，不另建任务

任务“已保存”只证明配置存在。首跑通过还需同时看到计划触发历史、目标逻辑日的 `COMMITTED` 收据和同日 `last_dream.md` 探针。

## 隐私与发布闸

普通本地检查：

```bash
python3 scripts/check.py
```

发布检查必须提供仓库外的私有标记表；缺失或空表会直接失败：

```bash
PGH_RELEASE_MODE=1 \
PGH_RELEASE_MARKS_FILE=/absolute/path/to/private-marks.txt \
python3 scripts/check.py --release
```

标记表每行一个禁止出现在公开仓或 Git 历史中的字符串，`#` 开头的行是注释。发布闸还会检查常见凭证、个人邮箱、真实主目录、内部 URI、符号链接、超大文件、运行态目录、Git 历史与工作树清洁度。

“内容完全脱敏”不等于托管账号匿名：把仓库 push 到个人 Git 托管账号后，账号名、组织名和平台侧活动仍可能公开。需要隐藏发布者身份时，应使用单独的公开组织或匿名发布账号。

## 目录

```text
.
├── CODEBUDDY.md
├── .codebuddy/
│   ├── agents/
│   ├── hooks/
│   ├── rules/
│   ├── settings.json
│   └── skills/
├── docs/
├── scripts/
├── tests/
└── workspace/
```

架构入口：

- [架构说明书](./workspace/02%20Meta%20Zone/Architecture/README.md)
- [初始化排程访谈](./docs/schedule_interview.md)
- [PGH 设计主文档](./docs/Predictive%20Generative%20Harness%20System%20v6.0.md)
- [核心层与 WorkBuddy 适配层分流](./docs/核心分流.md)

## 许可

MIT，见 [LICENSE](./LICENSE)。
