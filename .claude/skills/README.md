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
| `/fix-issue` | _(populate once the skill is defined)_ |
| `/refactor` | _(populate once the skill is defined)_ |

## Knowledge (background)

Loaded automatically by Claude when their descriptions match the task at hand.

| Skill | Covers |
|---|---|
| `color-system` | _(populate: palette, color tokens, usage rules)_ |
| `typography` | _(populate: fonts, type scale, weights)_ |
| `component-patterns` | _(populate: buttons, cards, forms, status pills, etc.)_ |
| `data-model` | _(populate: tables, relationships, query patterns for this domain)_ |
| `copy-patterns` | _(populate: voice rules, banned words, example phrasings)_ |

## Adding a skill

1. Decide if it's a command (user runs it) or knowledge (Claude loads it).
2. Create `skills/{name}/SKILL.md` with valid frontmatter — see the
   `agent-architect` agent at studio scope for the spec.
3. Add a row to this README under the right section.
