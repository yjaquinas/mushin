"""The intentionally small, hand-written Mushin guide catalog.

This is editorial content, not a generator: each guide is a distinct piece of
advice reviewed as a whole. Keeping it in structured Python makes route data,
related links, schema, and templates share one stable source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Guide:
    slug: str
    title: str
    description: str
    definition: str
    steps: tuple[str, ...]
    workflow: str
    limitation: str
    published_on: str
    related_slugs: tuple[str, ...]


PUBLISHED_ON = "2026-07-22"

GUIDES: tuple[Guide, ...] = (
    Guide(
        slug="what-is-a-practice-log",
        title="What is a practice log?",
        description="A plain-language guide to keeping a record of practice, without turning it into a performance review.",
        definition=(
            "A practice log is a small record of what you did, when you did it, and—if it helps—what you noticed. "
            "It is not a verdict on your discipline. Its job is to make a long stretch of ordinary sessions easier to see."
        ),
        steps=(
            "Choose one activity and give it a clear, plain name.",
            "After each session, log the date and a simple count that fits the practice.",
            "Add a short note only when it will be useful to meet your future self again.",
        ),
        workflow=(
            "In Mushin, create an activity, then add one entry after each practice. "
            "Use the count for completed sessions and notes for a detail you want to revisit. "
            "The activity history becomes a record you can browse without reconstructing the month from memory."
        ),
        limitation=(
            "A log can show that practice happened; it cannot judge its quality or explain every change in skill. "
            "Keep the record light enough that the act of logging does not compete with the practice itself."
        ),
        published_on=PUBLISHED_ON,
        related_slugs=("start-tracking-one-activity", "streaks-help-and-do-not"),
    ),
    Guide(
        slug="simple-habit-tracker-for-showing-up",
        title="A simple habit tracker for people who want to keep showing up",
        description="Use a simple habit tracker to notice return visits, not to turn one missed day into a failure.",
        definition=(
            "A simple habit tracker is a record of repeated actions. For many people, the useful question is not “Was I perfect?” "
            "but “Did I return to this thing often enough for it to have a place in my life?”"
        ),
        steps=(
            "Pick an action small enough to record honestly.",
            "Decide what counts before the week begins: one completed session or another unit that fits your practice.",
            "Review the pattern at the end of the week and adjust the definition if it is asking too much or too little.",
        ),
        workflow=(
            "Create an activity and add one entry for each completed session; a note can hold a brief observation. "
            "The calendar and history make the gaps and returns visible, while the total keeps the record grounded in actual sessions."
        ),
        limitation=(
            "A tracker is a mirror, not a coach. Travel, illness, caregiving, and changing priorities can interrupt a pattern for good reasons. "
            "Let the record describe that reality instead of using it to demand a streak."
        ),
        published_on=PUBLISHED_ON,
        related_slugs=("streaks-help-and-do-not", "progress-journal-versus-habit-tracker"),
    ),
    Guide(
        slug="track-a-habit-without-a-chore",
        title="How to track a habit without turning it into a chore",
        description="A low-pressure habit log that preserves the pleasure of the activity while making your time with it visible.",
        definition=(
            "A habit log records your contact with an activity, not your worth at it. "
            "It can be as simple as one completed session or another unit that feels natural to record."
        ),
        steps=(
            "Choose one unit that feels natural for the activity.",
            "Use one activity for the habit, or separate activities when you want distinct histories.",
            "Write down an observation only when you want to remember it; do not make extra writing a condition of showing up.",
        ),
        workflow=(
            "For a single focus, make one activity and add a count after each session. "
            "For a broader habit, use one activity and note the relevant context in each entry. Both approaches leave you with a practical answer to “when did I last pick this up?”"
        ),
        limitation=(
            "Counts are not a measure of attention, understanding, or the value of a session. "
            "Some practices invite a slower pace; a record should make room for that."
        ),
        published_on=PUBLISHED_ON,
        related_slugs=("what-is-a-practice-log", "start-tracking-one-activity"),
    ),
    Guide(
        slug="keep-a-training-log",
        title="How to keep a training log",
        description="A practical training log for sessions, drills, milestones, and notes worth returning to.",
        definition=(
            "A training log is a factual record of sessions and the details you may want to revisit. "
            "It helps separate the steady work of training from the fuzzy feeling that you have—or have not—done enough."
        ),
        steps=(
            "Track attendance first; it is the most dependable baseline.",
            "Add one count for each session, milestone, or focused block of work.",
            "Keep notes concrete: a drill, a correction, a question, or a piece of equipment—not a broad judgment of the session.",
        ),
        workflow=(
            "Set up a training activity and log one entry for each session. "
            "A brief note about a technique, drill, or question can be enough context for the next practice. "
            "If you track different kinds of training, separate activities can keep their records distinct."
        ),
        limitation=(
            "Attendance and volume do not replace instruction, recovery, or safe training decisions. "
            "A log can preserve observations, but it cannot diagnose pain or decide when to push through it."
        ),
        published_on=PUBLISHED_ON,
        related_slugs=("what-is-a-practice-log", "streaks-help-and-do-not"),
    ),
    Guide(
        slug="progress-journal-for-steady-study",
        title="A progress journal for steady study",
        description="Keep a progress journal that records practice choices and useful observations instead of chasing perfect consistency.",
        definition=(
            "A progress journal is a dated account of the work you chose to do. "
            "It gives your study a memory without pretending that every day should look the same."
        ),
        steps=(
            "Name the activity and choose a unit that matches it.",
            "Record the kind of practice in a note when that distinction matters to you.",
            "Look back monthly for what you actually return to, then use that evidence to plan the next few weeks.",
        ),
        workflow=(
            "Create an activity, then log a one-count entry after each study session. "
            "Brief notes about the session make the history more useful than a bare total while remaining quick to write."
        ),
        limitation=(
            "Time spent and units completed do not directly measure progress. "
            "Use the journal to notice your process, and leave room for slow periods and rest that do not fit a tidy count."
        ),
        published_on=PUBLISHED_ON,
        related_slugs=("progress-journal-versus-habit-tracker", "track-a-habit-without-a-chore"),
    ),
    Guide(
        slug="progress-journal-versus-habit-tracker",
        title="Habit tracker versus progress journal",
        description="Understand when a simple yes-or-no habit record is enough and when notes make a progress journal more useful.",
        definition=(
            "A habit tracker answers whether an action happened. A progress journal adds enough context to remember what happened and why it mattered. "
            "Neither is inherently better; they serve different levels of attention."
        ),
        steps=(
            "Start with a tracker when a simple completed/not-completed record is all you need.",
            "Use a journal when the kind of session changes the meaning of the record.",
            "Combine them by recording the session first and adding a short note only when context will help later.",
        ),
        workflow=(
            "In Mushin, the count on an activity can do the tracker’s job: one entry for one session. "
            "The entry note can do the journal’s job when you need it—for example, a brief note about the session or what you want to revisit."
        ),
        limitation=(
            "More detail is not automatically more useful. A dense journal can become difficult to maintain, while a simple tracker can hide meaningful differences. "
            "Choose the smallest record that supports the decision you want to make later."
        ),
        published_on=PUBLISHED_ON,
        related_slugs=(
            "simple-habit-tracker-for-showing-up",
            "progress-journal-for-steady-study",
        ),
    ),
    Guide(
        slug="streaks-help-and-do-not",
        title="How streaks help—and when they do not",
        description="Use streaks as a gentle signal of continuity, while avoiding the all-or-nothing pressure they can create.",
        definition=(
            "A streak is a run of consecutive periods in which you logged an activity. It can make a new rhythm visible, but it is only one view of a practice—not the practice itself."
        ),
        steps=(
            "Decide whether daily, weekly, or session-based continuity fits the activity.",
            "Treat a streak as information about a recent pattern, not as a score to defend.",
            "After a break, make the next honest entry instead of trying to repair the old run.",
        ),
        workflow=(
            "Mushin shows a current streak alongside an activity’s total and history. "
            "For an activity you expect to do daily, that can make regular return visits easy to notice. "
            "For a less frequent practice, the total sessions and dated history may say more than a daily streak."
        ),
        limitation=(
            "Streaks can make a rest day or interruption feel larger than it is. "
            "If the number starts pulling attention away from the activity, hide it in your own mind and return to a simpler question: what is the next session?"
        ),
        published_on=PUBLISHED_ON,
        related_slugs=("simple-habit-tracker-for-showing-up", "start-tracking-one-activity"),
    ),
    Guide(
        slug="start-tracking-one-activity",
        title="How to start tracking one activity in two minutes",
        description="A minimal setup for starting a useful activity record before you have a system to maintain.",
        definition=(
            "Starting a tracking habit does not require a dashboard, a goal, or a perfect category system. "
            "You need one activity and one honest first entry. The rest can become clearer after you have something real to look at."
        ),
        steps=(
            "Choose the activity you already expect to do next.",
            "Give it a plain name and create it.",
            "Log the next session with a count of one, then stop. Add detail only after you know what you wish you could remember.",
        ),
        workflow=(
            "In Mushin, create an activity. After the next session, add an entry. "
            "Later, the activity card, calendar, and history will have a real starting point without asking you to backfill a whole past."
        ),
        limitation=(
            "Two minutes is enough to begin, not a promise that every practice will fit into two minutes forever. "
            "The useful rule is to keep the recording step proportionate to the activity, especially when life gets busy."
        ),
        published_on=PUBLISHED_ON,
        related_slugs=("what-is-a-practice-log", "simple-habit-tracker-for-showing-up"),
    ),
)

_BY_SLUG = {guide.slug: guide for guide in GUIDES}


def guide_for_slug(slug: str) -> Guide | None:
    return _BY_SLUG.get(slug)


def related_guides(guide: Guide) -> tuple[Guide, ...]:
    return tuple(_BY_SLUG[slug] for slug in guide.related_slugs)
