---
name: sdd-impl-lite
description:
  Implement an existing plan from _sdd, tracking progress,
  verification and deviations in `<plan_folder_name>-impl.md`
argument-hint:
  Plan number, slug, or feature name (optional — inferred from current branch if
  omitted)
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

You are helping to implement a feature that already has an implementation plan
under `_sdd/`. Always adhere to any rules or requirements set out in any
CLAUDE.md files when responding.

User input: $ARGUMENTS

## High level behavior

Your job will be to:

- Identify the existing plan folder under `_sdd/` that matches
  `$ARGUMENTS` or the current branch
- Read the plan (and its spec) in full
- Implement the changes described in the plan's `## Files to Modify` section,
  working through the `## Task List` in order
- Never edit the plan file: once the plan is approved and implementation begins
  it is read-only. Track everything in
  `_sdd/<plan_folder_name>/<plan_folder_name>-impl.md` instead
- Check off each task in `<plan_folder_name>-impl.md` as it's completed,
  then record the implementation summary, verification results and deviations
  there

## Step 1. Identify the matching plan

- If `$ARGUMENTS` contains a plan/spec number (e.g. `00002`) or a slug/feature
  name, find the matching folder under `_sdd/` (folders matching
  `NNNNN-*` directly under `_sdd/`, ignoring
  `_sdd/templates/`) that contains `<folder>-plan.md`.
- If `$ARGUMENTS` is empty, check the current Git branch name
  (`git branch --show-current`). Branches created by `/sdd-spec-lite` follow the
  pattern `<agent>/feature/<feature_slug>` (the agent prefix can be anything, so
  take the part after `/feature/`), optionally with a trailing version
  suffix (`-01`, `-02`, ...). Match `<feature_slug>` against the slug portion of
  the folders under `_sdd/`: try the exact slug first, then retry with a
  trailing `-NN` removed.

If more than one plan folder matches, list the matches and ask the user which
one to use before continuing.

If no matching plan folder can be found, stop and ask the user to clarify which
plan this is, or to run `/sdd-plan-lite` first. Do not guess, and do not create
a new plan from this command.

Call the matched folder name `plan_folder_name` (the spec, plan and
implementation files of a feature all live in this one folder). The
implementation file is named `<plan_folder_name>-impl.md`, e.g.
`_sdd/00021-fix-delete-label/00021-fix-delete-label-impl.md`.

## Step 2. Read the plan and spec

Read `_sdd/<plan_folder_name>/<plan_folder_name>-plan.md` in full
(read-only), and also read the corresponding spec at
`_sdd/<plan_folder_name>/<plan_folder_name>-spec.md` (referenced
under the plan's `## Context` section) so the implementation stays consistent with the original
requirements and acceptance criteria.

If the plan has no `## Task List` section, stop and tell the user to regenerate
the plan with `/sdd-plan-lite` first — this command relies on it to track
progress.

## Step 3. Create or resume the implementation file

Progress lives in
`_sdd/<plan_folder_name>/<plan_folder_name>-impl.md`, next to the
plan.

- If it does not exist, create it from the structure in Step 6, copying the
  plan's `## Task List` items verbatim, all unchecked (`- [ ]`), and leaving the
  other sections empty.
- If it already exists, read it and resume: do not overwrite it, and treat items
  already checked (`- [x]`) as done.

## Step 4. Implement each task

Work through the `## Task List` items in `<plan_folder_name>-impl.md` in
order, top to bottom:

1. Skip any item already checked (`- [x]`).
2. For each unchecked item, make the corresponding change(s) described in the
   plan's `## Files to Modify`.
3. Immediately after finishing an item, edit `<plan_folder_name>-impl.md`
   to check it off (`- [ ]` → `- [x]`), so progress is saved incrementally
   rather than all at the end.
4. If a task can't be completed exactly as written (e.g. the plan is stale
   relative to the current code), make the best faithful judgment call, keep
   going, and note the deviation for `## Deviations` rather than stopping the
   whole run.

Do not implement anything listed under the plan's `## Out of Scope` section.
Never modify the plan file itself.

Never run `git add` or `git commit` (or otherwise commit, stage, push, or change
branches) as part of this command. Leave all changes uncommitted for the user to
review, and commit only if they explicitly ask.

## Step 5. Verify

Follow the steps under the plan's `## Verification` section as closely as
possible (running commands, clearing caches, checking behavior, etc.) to confirm
the implementation works as intended. Note the actual outcome of each
verification step — don't just assume it passed.

If a verification step fails, report it honestly. Do not start a fix-and-retry
loop: leave the verification task in the `## Task List` unchecked, and carry the
failure (what was run, what was observed) into `## Verification Results` and the
final output.

## Step 6. Write up the implementation file

Fill in the remaining sections of
`_sdd/<plan_folder_name>/<plan_folder_name>-impl.md` (keeping the
checked-off task list at the top). Use this structure:

```markdown
# Implementation: <feature-name>

Plan: `_sdd/<plan_folder_name>/<plan_folder_name>-plan.md`

## Task List

- [x] ...

## Implementation Summary

- ...

## Verification Results

- ...

## Deviations

- None.
```

- **Implementation Summary:** what was actually changed, file by file (brief —
  the plan's `## Files to Modify` has the detail)
- **Verification Results:** the result of each verification step (pass/fail and
  what was observed). If any step failed, start the section with a clearly
  marked line such as
  `**Verification failed:** <which step and what was observed>`
- **Deviations:** differences from the plan and why, and any task list items
  left unchecked and why; write `None.` if there are none

## Step 7. Final output to the user

After `<plan_folder_name>-impl.md` is written, respond to the user with a
short summary in this exact format:

```text
Implementation file: _sdd/<plan_folder_name>/<plan_folder_name>-impl.md
Tasks completed: <n>/<total>
```

Then a brief (3-5 bullet) summary of what changed and the verification result.
If verification failed, say so plainly in the first bullet. Do not repeat the
full plan or the appended summary verbatim in the chat unless the user
explicitly asks to see it.
