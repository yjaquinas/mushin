# Git commit conventions

## Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

<optional body>
```

Common types: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `perf`.

Scope is the affected area (e.g. `calendar`, `routes`, `templates`, `strings`).
Omit scope only when the change is truly cross-cutting.

## Rules

- Summary line: imperative mood, lowercase after the colon, no trailing period, ≤72 chars.
- Body: explain *why*, not *what* — the diff already shows what changed.
- Never add `Co-Authored-By: Claude` or any AI attribution trailer.
- Split into multiple commits when changes are logically independent (e.g. a
  refactor and a feature in the same session belong in separate commits).
