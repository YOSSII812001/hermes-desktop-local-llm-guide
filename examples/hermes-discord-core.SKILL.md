---
name: hermes-discord-core
description: Lightweight router for a dedicated Hermes Discord DM or channel.
---

# Hermes Discord Core

Use this skill only as a small routing layer.
Load the detailed skill for the selected task instead of reproducing its procedure here.

## Routing

- Code changes, tests, reviews, or pull requests: use the coding-agent dispatch skill.
- Obsidian note creation or homework updates: use the Obsidian operations skill.
- Hermes Gateway, Discord, local-model, or skill failures: use the Hermes operations skill.
- X post lookup: use the native `x_search` tool or its dedicated research skill.
- Simple summaries and short local file updates: use local file tools directly.

## Safety

- Never expose prompts, credentials, private identifiers, or raw command output in Discord.
- Do not start a second delegated task before checking the first task's state.
- Verify time-sensitive facts with an available tool.
- Report the result and the remaining user decision in plain Japanese.
