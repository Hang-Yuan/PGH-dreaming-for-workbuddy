---
alwaysApply: true
enabled: true
---

# WorkBuddy Adapter 规则

- 项目规则入口为 `CODEBUDDY.md` 与 `.codebuddy/rules/`。
- SessionStart 用于 startup/resume/clear/compact/fork 的身份上下文补注。
- UserPromptSubmit 用于已有历史会话的确定性补注和运行时提示。
- hook 输出使用 CodeBuddy 官方 JSON `hookSpecificOutput.additionalContext` 格式。
- 自动化只使用 WorkBuddy 原生任务，不使用 launchd、systemd、独立 cron 或其他宿主调度器。
- `workspace/` 是只读公开种子；初始化后身份补注只能读取 `.pgh/state.json` 指向的 `runtime/workspace/SOUL/persona/persona_SOUL.md` 与 `runtime/workspace/USER/USER.md`。
