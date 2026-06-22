"""Static guard: background-only color tokens must never be used as `text-*`.

`--color-brand`, `--color-obsidian`, and the `--color-surface-*` family are
background-only roles (see `.claude/skills/color-system/SKILL.md`). Using one
of them as a `text-*` foreground utility breaks dark-mode contrast: a fixed
token paired with a swapping one (or vice versa) can converge to the same
value in one theme, making the text invisible. This is a cheap, mechanical
regression guard — a grep over the rendered template tree — not a browser
test.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "app" / "templates"

# Background-only tokens that must never appear as a `text-*` foreground utility.
FORBIDDEN_TEXT_CLASSES = re.compile(r"\btext-(?:brand|obsidian|surface-[0-9])\b")

# Matches `class="..."` / `class='...'` attribute values (non-greedy, no
# nested quotes expected in Jinja2 templates' static class lists).
CLASS_ATTR = re.compile(r'class\s*=\s*"([^"]*)"|class\s*=\s*\'([^\']*)\'')


def _iter_template_files() -> list[Path]:
    return sorted(TEMPLATES_DIR.rglob("*.jinja2"))


def test_template_tree_is_discoverable() -> None:
    """Sanity check the path resolves before trusting an empty-violations result."""
    templates = _iter_template_files()
    assert templates, f"expected to find *.jinja2 files under {TEMPLATES_DIR}"


def test_no_background_only_tokens_used_as_text_color() -> None:
    """`text-brand`, `text-obsidian`, `text-surface-{n}` must never appear in class=.

    These tokens are background-only roles. See
    `.claude/skills/color-system/SKILL.md` ("Foreground/background pairing
    rule") for the dark-mode-invisibility bug class this guards against
    (found 2026-06-22, 10 instances).
    """
    violations: list[str] = []

    for template_path in _iter_template_files():
        text = template_path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for class_match in CLASS_ATTR.finditer(line):
                class_value = class_match.group(1) or class_match.group(2) or ""
                for token_match in FORBIDDEN_TEXT_CLASSES.finditer(class_value):
                    rel_path = template_path.relative_to(TEMPLATES_DIR.parent.parent)
                    violations.append(
                        f"{rel_path}:{line_no}: forbidden `{token_match.group(0)}` "
                        f'in class="{class_value}"'
                    )

    assert not violations, (
        "Background-only color tokens (--color-brand, --color-obsidian, "
        "--color-surface-*) must never be used as a text-* foreground color "
        "(see .claude/skills/color-system/SKILL.md). Offending spots:\n" + "\n".join(violations)
    )
