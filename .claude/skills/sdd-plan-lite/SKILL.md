---
name: sdd-plan-lite
description: Create an implementation plan file in _sdd for an existing spec
argument-hint:
  Spec number, slug, or feature name (optional — inferred from current branch if
  omitted)
allowed-tools: Read, Write, Glob, Bash(git branch:*)
---

You are helping to write a detailed implementation plan for a feature that
already has a spec under `_sdd/`. Always adhere to any rules or requirements
set out in any CLAUDE.md files when responding.

User input: $ARGUMENTS

## High level behavior

Your job will be to:

- Identify the existing spec folder under `_sdd/` that this plan
  belongs to
- Reuse that spec's exact numbered folder name (do not invent a new number — the
  spec, plan and implementation files of a feature share the same
  `<spec_folder_name>` folder)
- Write a detailed implementation plan markdown file into that same folder

Then save the plan file to disk and print a short summary of what you did.

## Step 1. Identify the matching spec

Determine which spec this plan is for:

- If `$ARGUMENTS` contains a spec number (e.g. `00002`) or a slug/feature name,
  find the matching folder under `_sdd/` (folders matching
  `NNNNN-*` directly under `_sdd/`, ignoring
  `_sdd/templates/`) that contains `<folder>-spec.md`.
- If `$ARGUMENTS` is empty, check the current Git branch name
  (`git branch --show-current`). Branches created by `/sdd-spec-lite` follow the
  pattern `<agent>/feature/<feature_slug>` (the agent prefix can be anything, so
  take the part after `/feature/`), optionally with a trailing version
  suffix (`-01`, `-02`, ...). Match `<feature_slug>` against the slug portion of
  the folders under `_sdd/`: try the exact slug first, then retry with a
  trailing `-NN` removed.

If more than one spec folder matches, list the matches and ask the user which
one to use before continuing.

If no matching spec folder can be found, stop and ask the user to clarify which
spec this plan is for, or to run `/sdd-spec-lite` first. Do not guess, and do
not create a new spec from this command.

Call the matched folder name `spec_folder_name` (e.g.
`00002-csv-comma-delimiter-import`).

## Step 2. Read the spec

Read `_sdd/<spec_folder_name>/<spec_folder_name>-spec.md` in full, paying
particular attention to the Functional Requirements, Possible Edge Cases,
Acceptance Criteria, and any answered Open Questions. The plan must be
consistent with the spec and must not contradict any answered Open Question.

If the `## Open Questions` section still contains the unreplaced template
placeholder (`<question>` / `ANSWER: <answer, once known>`), the spec is
unfinished: stop and tell the user to replace it with real questions or
`- None.` before continuing.

If the section lists no real questions (it is empty, or just says `None.` or
`...`), continue. Otherwise, if any Open Question is still unanswered (no
`ANSWER:` present next to it), stop and ask the user to answer it before
continuing, since the plan depends on it.

## Step 3. Draft the plan content

First check for an existing plan for this spec at:

- `_sdd/<spec_folder_name>/<spec_folder_name>-plan.md`

If it exists, do NOT overwrite it silently, and do not create a second plan next
to it. A sibling `<spec_folder_name>-impl.md` from `/sdd-impl-lite` may also
exist. Tell the user which file exists and ask whether to continue and
write a new plan at the folder path; if they decline or do not answer, stop
without changing anything.

Then create a markdown plan document using the exact structure defined in the
plan template file here: @.claude/skills/sdd-plan-lite/template.md. The plan
must:

- Reference the spec file path at the top, under `## Context`, along with a
  concise restatement of the current behavior and what changes per the spec's
  requirements and answered Open Questions
- List every file that needs to change, under `## Files to Modify`, with
  concrete details of what changes in each file (unlike the spec, code snippets
  and exact function/method names are encouraged here)
- Call out anything intentionally excluded from this change, under
  `## Out of Scope`
- Describe how to manually verify the change works, under `## Verification`
- End with a `## Task List` section: a checklist of concrete, checkable steps
  needed to implement the plan, using GitHub-flavored checkbox syntax
  (`- [ ] Do the thing`). Break the `## Files to Modify` section down into one
  task per file (or per logical change within a file, if a file has multiple
  distinct changes), in the order they should be implemented, plus a final task
  for running through `## Verification`. Every item starts unchecked (`- [ ]`) —
  `/sdd-impl-lite` copies this list into `<spec_folder_name>-impl.md` and
  checks it off there; the plan file itself is never edited during
  implementation.

Save it as:

`_sdd/<spec_folder_name>/<spec_folder_name>-plan.md`

(e.g.
`_sdd/00002-csv-comma-delimiter-import/00002-csv-comma-delimiter-import-plan.md`)

The folder already exists because it holds the spec.

## Step 4. Final output to the user

After the file is saved, respond to the user with a short summary in this exact
format:

```text
Spec: _sdd/<spec_folder_name>/<spec_folder_name>-spec.md
Plan file: _sdd/<spec_folder_name>/<spec_folder_name>-plan.md
```

Do not repeat the full plan in the chat output unless the user explicitly asks
to see it. The main goal is to save the plan file and report where it lives.
