---
alwaysApply: true
enabled: true
---

# PGH Core 规则（脱敏实验版）

- 运行治理与用户内容分离：`CODEBUDDY.md` / `.codebuddy/rules/` 是规则层，`workspace/` 是内容层。
- 身份层只在当前用户明确裁决后升级；实验运行不得自动写入身份层。
- L0 只读、episodic 与 semantic 为代谢工作区，白天不连续写入。
- 每日做梦必须以目标逻辑日为输入，先 A 段工作固化，再 B 段记忆代谢，失败不得伪造 COMMITTED 收据。
- 周级做梦由日链按目标日条件调用，不另建排程；季度只允许 detect。
- 任何模板发布前必须做脱敏扫描、路径扫描、秘密扫描和结构测试。
