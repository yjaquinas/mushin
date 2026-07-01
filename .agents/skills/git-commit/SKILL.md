---
name: git-commit
description: Stage and commit changes using Conventional Commits. Run this skill when the user asks to commit.
allowed-tools: Bash(git:*)
---

# git-commit skill

Create a git commit following the project's conventions.

## Steps

1. Run in parallel:
   - `git status` — see what's staged/unstaged/untracked
   - `git diff HEAD` — review all changes
   - `git log --oneline -5` — match the existing commit style

2. Decide how many commits are needed. Split when changes are logically
   independent (e.g. a bug fix and an unrelated refactor belong in separate
   commits). One coherent change = one commit.

3. For each commit:
   - Stage the relevant files with `git add <specific files>` — never `git add -A`
   - Write the message in **Conventional Commits** format:

     ```
     <type>(<scope>): <short summary>

     <optional body — explain why, not what>
     ```

   - Common types: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `perf`
   - Summary line: imperative mood, lowercase after the colon, no trailing period, ≤72 chars
   - Pass the message via heredoc to preserve formatting:

     ```bash
     git commit -m "$(cat <<'EOF'
     type(scope): summary

     Optional body.
     EOF
     )"
     ```

## Hard rules

- **Never** add `Co-Authored-By: Codex` or any AI attribution trailer.
- **Never** use `--no-verify`.
- **Never** amend a commit that has already been pushed.
- If a pre-commit hook fails, fix the underlying issue and create a new commit — do not `--amend`.
