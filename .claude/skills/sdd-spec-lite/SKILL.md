---
name: sdd-spec-lite
description: Create a feature spec file and branch from a short idea
argument-hint: agent=<name> Short feature description
allowed-tools: Read, Write, Glob, Bash(git switch:*), Bash(git status:*), Bash(git branch:*)
---

You are helping to spin up a new feature spec for this application, from a short
idea provided in the user input below. Always adhere to any rules or
requirements set out in any CLAUDE.md files when responding.

User input: $ARGUMENTS

## High level behavior

Your job will be to turn the user input above into:

- A human friendly feature title in kebab-case (e.g. new-heist-form)
- A safe git branch name not already taken, prefixed with the agent name (e.g.
  opencode/feature/new-heist-form)
- A detailed markdown spec file under a numbered folder inside the
  _sdd/ directory

The agent name is a required user parameter (`agent=<name>`); it is never
guessed.

Then save the spec file to disk and print a short summary of what you did.

## Step 0. Require the agent name

Look in `$ARGUMENTS` for `agent=<name>` (for example `agent=opencode`; typical
values are `claude`, `opencode`, `agy`, `gemini`, but any name is accepted).

Normalise `<name>` to `agent_slug`: lowercase, only `a-z`, `0-9` and `-`,
spaces and punctuation replaced with `-`, multiple `-` collapsed, `-` trimmed
from start and end.

If `agent=` is missing, or `agent_slug` is empty, STOP. Do not run any git
command, switch branches or create files. Tell the user that the agent name
is required and ask them to run the command again with it, e.g.
`/sdd-spec-lite agent=opencode <feature idea>`. Do NOT guess a default such as
`claude`.

The rest of `$ARGUMENTS`, with the `agent=<name>` part removed, is the feature
idea used in Step 2. If nothing remains, ask the user for the feature idea.

## Step 1. Check the working tree

Run `git branch --show-current` and `git status --porcelain`.

If the working tree is clean, continue to Step 2.

If there are any uncommitted, unstaged, or untracked files, do NOT abort. List
them for the user, explain that the new branch will carry them along (they will
not be staged or committed by this command), and ask whether to continue anyway.
If the user declines or does not answer, stop and DO NOT GO ANY FURTHER.

## Step 2. Parse the arguments

From `$ARGUMENTS` (without the `agent=` part), extract:

1. `feature_title`
   - A short, human readable title in kebab-case.
   - Example: "card-component-for-dashboard-stats".

2. `feature_slug`
   - A git safe slug derived from `feature_title`.
   - Rules:
     - Lowercase
     - Kebab-case
     - Only `a-z`, `0-9` and `-`
     - Replace spaces and punctuation with `-`
     - Collapse multiple `-` into one
     - Trim `-` from start and end
     - Maximum length 40 characters
   - Example: `card-component` or `card-component-dashboard`.

3. `branch_name`
   - Format: `<agent_slug>/feature/<feature_slug>`
   - Example: `opencode/feature/card-component`.

4. `spec_number`
   - A 5-digit, zero-padded, incrementing sequence number (e.g. `00001`,
     `00002`, ...).
   - Determine it by listing the existing numeric-prefixed folders directly
     under `_sdd/` (folders matching `NNNNN-*`), taking the
     highest existing number, and incrementing by 1. If none exist, start at
     `00001`.
   - Only look at top-level folders in `_sdd/` for this (ignore
     files and the `templates/` folder).

5. `spec_folder_name`
   - Format: `<spec_number>-<feature_slug>`
   - Example: `00001-card-component`.

If you cannot infer a sensible `feature_title` and `feature_slug`, ask the user
to clarify instead of guessing.

## Step 3. Switch to a new Git branch

Before making any content, switch to a new Git branch using the `branch_name`
derived from the `$ARGUMENTS`.

Check whether the name is taken with `git branch --list <branch_name>`. If it
is, append a two-digit version number, starting at `-01` and incrementing until
the name is free: e.g. `opencode/feature/card-component-01`.

Only the branch name gets the version suffix. `feature_slug` and
`spec_folder_name` stay unchanged (`/sdd-plan-lite` and `/sdd-impl-lite` ignore a
trailing `-NN` on the branch when matching it to a folder).

## Step 4. Draft the spec content

Create a markdown spec document that a planning step can use directly. Save it
as:

`_sdd/<spec_folder_name>/<spec_folder_name>-spec.md`

(e.g. `_sdd/00001-card-component/00001-card-component-spec.md`)

Create the folder if it does not already exist. Use the exact structure as
defined in the spec template file here:
@.claude/skills/sdd-spec-lite/template.md. Do not add technical
implementation details such as code examples.

Set the template's `branch:` line to the actual branch you switched to in Step 3
(including the agent prefix and any `-NN` version suffix), not the unsuffixed
`branch_name`.

In `## Open Questions`, write each question as a list item and, once it is
answered, put the answer on an indented `ANSWER:` line directly beneath it. If
there are no open questions, write `- None.` and remove the template's
placeholder text.

## Step 5. Final output to the user

After the file is saved, respond to the user with a short summary in this exact
format:

```text
Branch: <branch_name>
Spec file: _sdd/<spec_folder_name>/<spec_folder_name>-spec.md
Title: <feature_title>
```

Do not repeat the full spec in the chat output unless the user explicitly asks
to see it. The main goal is to save the spec file and report where it lives and
what branch name to use.
