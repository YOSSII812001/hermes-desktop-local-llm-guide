# Hermes Local Operations

This file contains operational rules for work performed from Hermes home.
Personality and user preferences belong in `SOUL.md` and `memories/USER.md`.

## Canonical Paths

- Confirm the active Desktop config path before editing.
- Use `%LOCALAPPDATA%\hermes` only after confirming it is the active profile.
- Store credentials in `.env` or the operating system's credential manager.
- Never copy credentials into Markdown, logs, backups, or public repositories.

## Tool And File Safety

- Do not read `.env`, `auth.json`, databases, or lock files.
- Limit file searches to the smallest directory needed for the task.
- Do not edit existing Obsidian notes unless the user asks for that edit.
- Use placeholders for user names, channel IDs, and local paths in public docs.

## Delegation

- Handle short summaries and simple note creation with local tools.
- Use a coding agent for code changes, tests, reviews, or multi-file investigation.
- Do not delegate the same task again before checking its existing state and output.

## Verification

- Read changed files back after writing them.
- Validate YAML after changing `config.yaml`.
- Start a new session after changing memory or channel skill bindings.
- Confirm behavior through the same CLI, Desktop, or Gateway path used by the user.
