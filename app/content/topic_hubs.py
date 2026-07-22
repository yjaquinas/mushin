"""Editorial registry for the small set of approved public topic hubs.

Topics are deliberately hand-authored.  Matching is limited to the explicit
activity names listed here; this module never classifies people from free text.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopicHub:
    slug: str
    title: str
    description: str
    definition: str
    activity_names: tuple[str, ...]
    guide_slugs: tuple[str, ...]
    approved: bool = False


# First-release editorial choices.  ``approved`` is the product-owner gate;
# publishing still also requires five qualifying public activities at request
# time.  Additions need an editorial review, not a new user-generated URL.
TOPIC_HUBS: tuple[TopicHub, ...] = (
    TopicHub(
        slug="reading",
        title="Reading logs",
        description="Explore public reading records from people who chose to make their practice discoverable.",
        definition=(
            "This collection is for activity records explicitly named Reading, Books, or Book reading. "
            "It shows a small set of public logs, not a judgment about what or how anyone reads."
        ),
        activity_names=("reading", "books", "book reading"),
        guide_slugs=("what-is-a-practice-log", "start-tracking-one-activity"),
        approved=True,
    ),
    TopicHub(
        slug="language-study",
        title="Language-study logs",
        description="Explore public language-study records from people who chose to make their practice discoverable.",
        definition=(
            "This collection is for activity records explicitly named Language study, Language learning, or Vocabulary. "
            "It does not identify a language, level, background, or goal from someone’s notes."
        ),
        activity_names=("language study", "language learning", "vocabulary"),
        guide_slugs=("progress-journal-for-steady-study", "track-a-habit-without-a-chore"),
        approved=True,
    ),
)

_BY_SLUG = {topic.slug: topic for topic in TOPIC_HUBS}


def topic_for_slug(slug: str) -> TopicHub | None:
    return _BY_SLUG.get(slug)
