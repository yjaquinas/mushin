# Skills — project scope

Top-level `skills/` is flat by design (Claude Code's skill discovery only scans
the top level for `SKILL.md` files — subdirectories silently disappear). This
README is the categorization layer.

Project-scope skills override or specialize studio-scope skills. For example,
`color-system` here defines *this project's* palette; `copy-patterns` encodes
*this project's* voice.

## Commands (user-invocable)

Appear in the `/` picker. Each is a slash command scoped to this project.

| Command | Purpose |
|---|---|
| `/fix-issue` | _(deferred — not yet defined)_ |
| `/refactor` | _(deferred — not yet defined)_ |

## Knowledge (background)

Loaded automatically by Claude when their descriptions match the task at hand.

| Skill | Covers |
|---|---|
| `data-model` | Category→activity→entry model, field_def/entry_value recipe, count modes, progression gates, derived-status rule, owner_id/index conventions |
| `copy-patterns` | Plain warm US-English voice, understated 無心 tone, banned gamer-loanwords, no-account/guest copy, centralized-strings i18n |
| `color-system` | _(stub — renderer-agnostic color tokens, filled as the UI lands)_ |
| `typography` | _(stub — type scale + home-card hero hierarchy, filled as the UI lands)_ |
| `component-patterns` | _(stub — activity card, quick-add, chip-group, progress bar, calendar/heatmap)_ |

## Adding a skill

1. Decide if it's a command (user runs it) or knowledge (Claude loads it).
2. Create `skills/{name}/SKILL.md` with valid frontmatter — see the
   `agent-architect` agent at studio scope for the spec.
3. Add a row to this README under the right section.
