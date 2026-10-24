# Git Commit Conventions

- **Never commit unless the user explicitly asks** ("commit" or equivalent).
  Make changes and leave them uncommitted until approved.
- **The agent name is a required user parameter.** When the user asks for a
  commit, they must give the agent name in the request (for example
  `commit, agent=opencode`). If it is missing, do not stage or commit anything:
  ask the user for it and wait. Do not infer it, and do not fall back to a
  default.
- **Never push, amend, rebase, force-push, or use `--no-verify`** unless the
  user explicitly asks.
- Commit directly on the current branch. Do not create branches.
- Use only plain `git` CLI commands for staging and committing. No GUI or MCP
  tools.
- **Never stage files unless the user explicitly asks** (a request to commit
  counts). When staging, stage only files changed in the current session, by
  explicit path. Never use `git add .` or `git add -A`. If a file also contains
  unrelated changes, do not stage it. Tell the user instead.
- Before committing, run `git status` and `git diff --cached --name-only` and
  confirm only the intended files are staged.
- One logical change per commit. Split unrelated changes into separate commits.
- Subject: imperative mood, no trailing dot, under 72 characters.
- Body: wrapped at 72 characters. Explain what changed and why, not a
  line-by-line restatement of the diff.
- **Trailer (mandatory on every commit):** add this as the last line, with the
  placeholders filled in.

  `Co-Authored-By: <agent name> (<model name>) <noreply@agent-domain>`

  - `<agent name>` is the display name for the `agent=` value the user gave:
    match the value case-insensitively against this table, and write the value
    exactly as typed if it is not in the table.

    | `agent=`   | `<agent name>` |
    | ---------- | -------------- |
    | `claude`   | `Claude Code`  |
    | `opencode` | `opencode`     |
    | `agy`      | `Antigravity`  |
    | `gemini`   | `Gemini CLI`   |
    | `continue` | `Continue`     |

  - `<model name>` is the exact model you are running as.
  - `<agent-domain>` is the tool's own domain, only if you know it for certain.
    Never invent a domain.
  - If a value is unknown, use `unknown model` or `ai.local`.

  The example below is only an illustration. Use the agent name given by the
  user and your own model name, not the ones shown.

- Preferred format (the heredoc avoids quoting problems). Keep the lines
  flush-left, with `EOF` at the start of its line:

```bash
git add path/to/file
git commit -F - <<'EOF'
Fix SSH command quoting

Explain what changed and why here.

Co-Authored-By: Example Agent (Example Model 1.0) <noreply@example.com>
EOF
```

- Before running `git commit`, confirm the agent name was provided by the user
  and the message contains the trailer.
