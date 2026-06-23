"""Centralized English UI copy for the web renderer.

Every user-facing string in ``app/templates/web/**`` and
``app/templates/components/**`` comes from this module — no hardcoded copy
in templates (grep-checked by
``tests/integration/test_web.py::test_no_hardcoded_copy_in_templates``).

Voice (see ``.claude/skills/copy-patterns``): plain, warm, second person, no
hype, no urgency/guilt framing. The "Mushin 無心" brand mark always ships
together and is never explained beyond the one-line gloss.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------

APP_NAME = "Mushin"
APP_NAME_HANJA = "無心"
APP_WORDMARK = "Mushin 無心"
APP_GLOSS = "No-mind. Just show up, and watch it add up."

# ---------------------------------------------------------------------------
# Entry screen (first run)
# ---------------------------------------------------------------------------

ENTRY_TITLE = "Mushin"
ENTRY_TAGLINE = "A record of what you keep showing up for"

ENTRY_AUTH_TAB_LOGIN = "Log in"
ENTRY_AUTH_TAB_CREATE = "Create account"

ENTRY_LOGIN_SUBMIT = "Log in"
ENTRY_CREATE_SUBMIT = "Create account"

ENTRY_FIELD_USERNAME = "Username"
ENTRY_FIELD_PASSWORD = "Password"
ENTRY_FIELD_EMAIL = "Email"
ENTRY_FIELD_EMAIL_HELP = "For account recovery. Optional."

ENTRY_CONSENT_CHECKBOX = "I agree to the Privacy Policy"

# RETIRED — guest mode removed 2026-06-16, drain-window cleanup pending
ENTRY_GUEST_LINK = "Continue without an account"
# RETIRED — guest mode removed 2026-06-16, drain-window cleanup pending
ENTRY_GUEST_SUB = (
    "Start now, connect an account later — your record is kept on our server either way."
)

ENTRY_DEMO_LINK = "See an example record →"

ENTRY_CONSENT_NOTICE = "By creating an account or continuing, you agree to our"
ENTRY_CONSENT_LINK_TEXT = "Privacy Policy"
ENTRY_CONSENT_SUFFIX = " (required)."

# Inline form errors — mirror app/auth/routes.py's HTTPException details.
ENTRY_ERROR_USERNAME_SHAPE = (
    "Username must be 3-20 characters: lowercase letters, numbers, and underscores only."
)
ENTRY_ERROR_USERNAME_TAKEN = "That username is already taken."
ENTRY_ERROR_LOGIN_FAILED = "That username or password isn't right."
ENTRY_ERROR_GENERIC = "Something went wrong. Please try again."

# ---------------------------------------------------------------------------
# Home (character sheet)
# ---------------------------------------------------------------------------

HOME_TITLE = "Your activities"
HOME_EMPTY = "Nothing started yet."

# One-shot flash confirmation shown after a successful /account/visibility
# save (see app/routes/web.py — the flash cookie is read once, then cleared).
# Carries only the public/private state — no other personal data.
HOME_FLASH_VISIBILITY_PUBLIC = "Profile set to public."
HOME_FLASH_VISIBILITY_PRIVATE = "Profile set to private."

# ---------------------------------------------------------------------------
# Empty-state example categories + create-category
# ---------------------------------------------------------------------------

HOME_EXAMPLES_HINT = "Try one of these, or make your own."
HOME_EXAMPLE_ADD = "Add"
HOME_START_FROM_SCRATCH = "or start from scratch"
HOME_ADD_ACTIVITY = "Add an activity"

ACTIVITY_NEW_TITLE = "New activity"
ACTIVITY_FORM_NAME_LABEL = "Name"
ACTIVITY_FORM_NAME_PLACEHOLDER = "e.g. Workout"
ACTIVITY_FORM_SUBMIT = "Create"
ACTIVITY_FORM_CANCEL = "Cancel"
ACTIVITY_FORM_NAME_REQUIRED = "Activity name is required"

# Hero numeral suffixes / labels
HOME_COUNT_UNIT = "times"  # generic running-count unit ("3 times")
HOME_RUNNING_LABEL = "Total"

SUBTALLY_LOG_BUTTON = "New Entry"
HOME_STREAK_LABEL = "Streak"
HOME_STREAK_DAYS_UNIT = " days"

# ---------------------------------------------------------------------------
# Quick-add / log sheet
# ---------------------------------------------------------------------------

LOG_SHEET_TITLE = "Log"
LOG_SUBMIT = "Save entry"
LOG_CANCEL = "Close"

LOG_OCCURRED_AT_LABEL = "Date"
LOG_TIME_ADD = "Add a time"
LOG_MEMO_LABEL = "Memo"
LOG_MEMO_PLACEHOLDER = "Optional description"
LOG_COUNT_LABEL_SUFFIX = ""  # field_def.label is used directly
LOG_SCALE_LABEL_SUFFIX = ""

LOG_NOTES_LABEL = "Notes"
LOG_NOTES_PLACEHOLDER = "How'd it go? Add #tags anywhere."

LOG_SUCCESS_NOTICE = "Logged."

# ---------------------------------------------------------------------------
# Match-list sub-form (tournament entries)
# ---------------------------------------------------------------------------

MATCH_LIST_OPPONENT_LABEL = "Opponent"
MATCH_LIST_SCORE_LABEL = "Score"
MATCH_LIST_RESULT_LABEL = "Result"

MATCH_RESULT_WIN = "Win"
MATCH_RESULT_LOSS = "Loss"
MATCH_RESULT_DRAW = "Draw"

MATCH_LIST_ADD_ROW = "+ Add match"
MATCH_LIST_REMOVE_ROW = "Remove"

# ---------------------------------------------------------------------------
# Sub-tally detail screen
# ---------------------------------------------------------------------------

DETAIL_BACK = "Home"

# Inline rename form (sub-tally heading)
RENAME_SLUG_NOTICE = (
    "Renaming will change your share link. The old link will stop working."
)
RENAME_LABEL = "Rename activity"
RENAME_SAVE = "Save"
RENAME_CANCEL = "Cancel"

# Activity delete (two-step confirm from rename form)
ACTIVITY_DELETE = "Delete activity"
ACTIVITY_DELETE_CONFIRM_BODY = (
    "Delete this activity and everything in it — entries and notes. This can't be undone."
)
ACTIVITY_DELETE_CONFIRM = "Delete activity"
ACTIVITY_DELETE_CANCEL = "Keep"

# ---------------------------------------------------------------------------
# Competition stats (tournament sub-tallies with a match_list field)
# ---------------------------------------------------------------------------

STATS_TITLE = "Record"

STATS_RECORD_WINS = "W"
STATS_RECORD_LOSSES = "L"
STATS_RECORD_DRAWS = "D"

STATS_WIN_RATE_LABEL = "Win rate"
STATS_WIN_RATE_NONE = "No record yet"
STATS_WIN_RATE_BASIS_PREFIX = "Based on"
STATS_WIN_RATE_BASIS_UNIT = " decided matches"

STATS_TIMELINE_TITLE = "Recent matches"
STATS_TIMELINE_EMPTY = "No matches logged yet."

STATS_HEAD_TO_HEAD_TITLE = "Head-to-head"
STATS_HEAD_TO_HEAD_EMPTY = "No opponent record yet."

# ---------------------------------------------------------------------------
# Stats: counts, streak, calendar, heatmap
# ---------------------------------------------------------------------------

STATS_SUMMARY_TITLE = "Summary"
STATS_COUNTS_LABEL = "Counts"
STATS_STREAKS_LABEL = "Streaks"

STATS_PERIOD_WEEK = "This week"
STATS_PERIOD_MONTH = "This month"
STATS_PERIOD_YEAR = "This year"
STATS_PERIOD_LIFETIME = "All time"
STATS_AVG_PER_WEEK = "Weekly average"

STREAK_CURRENT_LABEL = "Current streak"
STREAK_LONGEST_LABEL = "Longest streak"
STREAK_DAY_UNIT = " day"
STREAK_DAYS_UNIT = " days"

CALENDAR_TITLE = "Calendar"
CALENDAR_PREV_MONTH = "Previous month"
CALENDAR_NEXT_MONTH = "Next month"
CALENDAR_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CALENDAR_DAY_ENTRIES_TITLE = "Entries on this day"
CALENDAR_DAY_ENTRIES_EMPTY = "No entries on this day."
CALENDAR_DAY_CLOSE = "Close"
CALENDAR_BACK_TO_CALENDAR = "Calendar"

# Heatmap strip: non-interactive, so HEATMAP_ARIA carries all the
# accessibility information for the whole strip; individual week-bars are
# aria-hidden. {active_weeks} interpolated by the template. Covers the
# current calendar year (fixed-length, future weeks zero-filled) — quarter
# labels (HEATMAP_QUARTER_LABELS) orient the reader within the strip instead
# of a window-length caption.
HEATMAP_ARIA = "Activity this year, {active_weeks} weeks with activity"
HEATMAP_EMPTY = "No activity yet"

# Quarter-start month labels placed along the heatmap strip (sparse — every
# week is a column, but only the week containing a quarter's 1st gets a text
# label, keyed by month number so the template can index directly off a
# bucket's `quarter_month`).
HEATMAP_QUARTER_LABELS = {1: "Jan", 4: "Apr", 7: "Jul", 10: "Oct"}

TAGS_TOP_HEADING = "Top tags"

# ---------------------------------------------------------------------------
# History: period switcher + actual log
# ---------------------------------------------------------------------------

HISTORY_PERIOD_SWITCHER_LABEL = "Select period"
HISTORY_PERIOD_WEEK = "Week"
HISTORY_PERIOD_MONTH = "Month"
HISTORY_PERIOD_ALL = "All"

HISTORY_PREV_WEEK = "Previous week"
HISTORY_NEXT_WEEK = "Next week"

HISTORY_LOG_TITLE = "Log"
HISTORY_LOG_EMPTY = "Nothing logged in this period."
HISTORY_CLEAR_SELECTION = "Clear selection"

# ---------------------------------------------------------------------------
# Tag-frequency / scale-distribution sections
# ---------------------------------------------------------------------------

TAG_FREQUENCY_EMPTY = "No tags logged yet."
TAG_FREQUENCY_THIS_WEEK = "This week"
TAG_FREQUENCY_THIS_MONTH = "This month"
TAG_FREQUENCY_THIS_YEAR = "This year"

SCALE_DISTRIBUTION_EMPTY = "Nothing logged yet."
SCALE_DISTRIBUTION_AVERAGE_LABEL = "Average"

# ---------------------------------------------------------------------------
# Theme toggle (masthead)
# ---------------------------------------------------------------------------

# Each label describes the *current* theme state plus the action a tap
# performs (toggle: light <-> dark).
THEME_TOGGLE_LABEL_LIGHT = "Theme: light. Switch to dark."
THEME_TOGGLE_LABEL_DARK = "Theme: dark. Switch to light."

# ---------------------------------------------------------------------------
# Footer (Privacy + Account) and account-page data/session actions
# ---------------------------------------------------------------------------

FOOTER_PRIVACY = "Privacy Policy"
FOOTER_ACCOUNT = "Account"

# Export/import/logout live on the /account page (not the footer) but keep
# their FOOTER_* names — the names predate the move and the copy itself
# isn't footer-specific, so renaming would just duplicate content.
FOOTER_EXPORT_DATA = "Export my data"
FOOTER_IMPORT_DATA = "Import data"
FOOTER_LOGOUT = "Log out"
FOOTER_DELETE_DATA = "Delete my data"

# Delete-my-data confirm dialog (account page)
DELETE_DATA_TITLE = "Delete all of your data?"
DELETE_DATA_BODY = "This deletes every record kept under this device — activities, sub-tallies, entries, and memos. This can't be undone."
DELETE_DATA_CONFIRM = "Delete my record"
DELETE_DATA_CANCEL = "Go back"

# Import-data confirm dialog (footer)
IMPORT_DATA_TITLE = "Replace all data with this file?"
IMPORT_DATA_BODY = "This replaces everything currently stored under this account — activities, sub-tallies, entries, and memos — with the contents of the uploaded file. This can't be undone."
IMPORT_DATA_FILE_LABEL = "Export file (.json)"
IMPORT_DATA_CONFIRM = "Replace my data"
IMPORT_DATA_CANCEL = "Go back"
IMPORT_DATA_ERROR_TOO_LARGE = "That file is too large to import."
IMPORT_DATA_ERROR_INVALID_FILE = "That doesn't look like a valid export file (.json)."
IMPORT_DATA_ERROR_VALIDATION = "Import failed: {reason}"

# ---------------------------------------------------------------------------
# Visibility consent (one-time screen, before first /home use)
# ---------------------------------------------------------------------------

# Factual, no alarm framing — same register as the account-deletion
# consequence copy (the user is making this choice themselves).
VISIBILITY_CONSENT_TITLE = "Who can see your record"
VISIBILITY_CONSENT_INTRO = (
    "You have a profile page, and it's findable by your username. Choose how much"
    " of your record it shows. You can change this later in your account settings."
)

VISIBILITY_CONSENT_PRIVATE_LABEL = "Private"
VISIBILITY_CONSENT_PRIVATE_DESC = (
    "Visitors see your activity names and counts — but"
    " not your individual entries or notes. Anyone you connect with as a fellow"
    " sees everything, including your notes."
)

VISIBILITY_CONSENT_PUBLIC_LABEL = "Public"
VISIBILITY_CONSENT_PUBLIC_DESC = (
    "Your whole record — every activity, entry, and note — is visible to anyone"
    " who has your profile link, and public records can turn up in tag search."
)

VISIBILITY_CONSENT_PRIVACY_PREFIX = "See our"
VISIBILITY_CONSENT_PRIVACY_LINK_TEXT = "Privacy Policy"
VISIBILITY_CONSENT_PRIVACY_SUFFIX = "for the details."

VISIBILITY_CONSENT_SUBMIT = "Continue"

# ---------------------------------------------------------------------------
# Account settings page (/account) — visibility toggle
# ---------------------------------------------------------------------------

# Same factual, no-alarm register as the consent screen. The toggle restates
# the consequence briefly on each change (not the full first-run explainer).
ACCOUNT_TITLE = "Account settings"

# Secondary, in-content way back home — the global header logo already links
# home on every page; this is a clearly labeled additional affordance, not a
# new nav system.
ACCOUNT_HOME_LINK = "Back to Home"

ACCOUNT_VISIBILITY_HEADING = "Who can see your record"
# The username doubles as a public handle — frame it as the share link.
# {username} is interpolated by the template.
ACCOUNT_VISIBILITY_SHARE_LINK = "Your profile is shareable at mushin.aqnas.xyz/@{username}"

# Current state line shown above the toggle.
ACCOUNT_VISIBILITY_CURRENT_PRIVATE = "Your record is private."
ACCOUNT_VISIBILITY_CURRENT_PUBLIC = "Your record is public."

# Radio labels mirror the consent screen.
ACCOUNT_VISIBILITY_PRIVATE_LABEL = "Private"
ACCOUNT_VISIBILITY_PRIVATE_DESC = (
    "Visitors see your activity names and counts, but not your entries"
    " or notes. Fellows you connect with see everything."
)
ACCOUNT_VISIBILITY_PUBLIC_LABEL = "Public"
ACCOUNT_VISIBILITY_PUBLIC_DESC = (
    "Your whole record — every activity, entry, and note — is visible to anyone"
    " who has your profile link, and can turn up in tag search."
)

ACCOUNT_VISIBILITY_SAVE = "Save"

# ---------------------------------------------------------------------------
# Sharing consent (connection-accept consequence screen)
# ---------------------------------------------------------------------------

# Shown when you accept a connection so it becomes a fellow link. Consumed by
# the Task 6 accept UI. Same calm, factual, no-alarm register as the visibility
# consent — the user is making this choice themselves. States the mutual
# exposure plainly: a fellow connection lifts the private gate in *both*
# directions.
SHARING_CONSENT_TITLE = "Connecting as fellows"

# Send-side: shown before a request is sent — nothing has happened yet, so
# this must not claim exposure has already occurred. States the request
# itself is inert, then restates the real consequence of the other person
# accepting later.
SHARING_CONSENT_BODY_SEND = (
    "Sending a request doesn't share anything yet — it just lets the other"
    " person decide. If they accept, you'll each see the other's full"
    " record — every activity, entry, and note — even the parts you keep"
    " private. Free-text notes can hold anything you've written there,"
    " including things you'd consider sensitive. You can remove the"
    " connection anytime, which takes away that access in both directions"
    " right away. You can also block someone instead, quietly."
)

# Accept-side: shown right before accepting, which is the actual moment the
# exposure happens — the plain consequence statement applies as-is.
SHARING_CONSENT_BODY_ACCEPT = (
    "Once you're fellows, you'll each see the other's full record — every"
    " activity, entry, and note — even the parts you keep private. Free-text"
    " notes can hold anything you've written there, including things you'd"
    " consider sensitive. You can remove the connection anytime, which takes"
    " away that access in both directions right away. You can also block"
    " someone instead, quietly."
)
SHARING_CONSENT_PRIVACY_PREFIX = "See our"
SHARING_CONSENT_PRIVACY_LINK_TEXT = "Privacy Policy"
SHARING_CONSENT_PRIVACY_SUFFIX = "for the details."
SHARING_CONSENT_CONFIRM = "Connect as fellows"
SHARING_CONSENT_CONFIRM_ACCEPT = "Accept and connect"
SHARING_CONSENT_CANCEL = "Not now"

# ---------------------------------------------------------------------------
# Private redefinition (one-time re-consent interstitial)
# ---------------------------------------------------------------------------

# Shown once to a pre-existing private account whose meaning of "Private"
# changed under them. Calm, factual — no alarm, no implication they did
# anything wrong; just what changed and an acknowledgement.
REDEFINITION_TITLE = "What “Private” means has changed"
REDEFINITION_BODY = (
    "Your record is set to Private. That used to mean your page showed nothing"
    " to visitors. Now a private page shows your activity names and counts to"
    " anyone who visits or finds you in search. Your individual"
    " entries and your notes stay private — only fellows you connect with see"
    " everything. Nothing else about your account changed."
)
REDEFINITION_PRIVACY_PREFIX = "See our"
REDEFINITION_PRIVACY_LINK_TEXT = "Privacy Policy"
REDEFINITION_PRIVACY_SUFFIX = "for the details."
REDEFINITION_ACKNOWLEDGE = "Got it"

# ---------------------------------------------------------------------------
# Privacy policy page
# ---------------------------------------------------------------------------

PRIVACY_PAGE_TITLE = "Privacy Policy"

# ---------------------------------------------------------------------------
# Public profiles (/@{username}, /@{username}/{slug})
# ---------------------------------------------------------------------------

# Retained for the legacy private-stub copy referenced in older tests/docs;
# the limited (character-sheet) view below is what visitors actually see on
# a private account now (three-tier visibility, see copy-patterns).
PROFILE_PRIVATE = "This record is private."

PROFILE_ACTIVITIES_EMPTY = "Nothing logged yet."
PROFILE_BACK_TO_PROFILE = "Back to @{username}"

# Quiet line under the character-sheet (limited) view of a private account —
# factual, no lock icon, no "request access" framing.
PROFILE_LIMITED_NOTICE = "Fellows see the full record, including notes."

# Owner-view notice on a public activity page — factual, no alarm framing.
ACTIVITY_PUBLIC_NOTICE = "This page is public — anyone with the link sees it, notes included."

# ---------------------------------------------------------------------------
# Entry edit-in-place
# ---------------------------------------------------------------------------

ENTRY_EDIT = "Edit"
ENTRY_SAVE = "Save"
ENTRY_CANCEL = "Cancel"
ENTRY_DELETE = "Delete"
ENTRY_DELETE_CONFIRM_BODY = "Delete this entry. This can't be undone."
ENTRY_DELETE_CONFIRM = "Delete"
ENTRY_DELETE_CANCEL = "Keep"

# ---------------------------------------------------------------------------
# Fellows + requests (social graph, Task 6)
# ---------------------------------------------------------------------------

FELLOWS_HEADING = "Fellows"
# {count} interpolated by the template. Used for non-owner/non-fellow
# viewers, who see only the number, never the clickable names.
FELLOWS_COUNT_LABEL = "{count} fellows"
FELLOWS_COUNT_LABEL_ONE = "1 fellow"
FELLOWS_EMPTY = "No fellows yet."

REQUESTS_HEADING = "Requests"
REQUESTS_INCOMING_EMPTY = "No pending requests."
REQUESTS_OUTGOING_HEADING = "Requested"
REQUESTS_ACCEPT = "Accept"
REQUESTS_DECLINE = "Decline"
REQUESTS_CANCEL = "Cancel"
# {count} interpolated by the template — a content-free badge.
REQUESTS_PENDING_BADGE = "{count}"

# Relationship-state affordance on another user's profile.
CONNECT_ACTION = "Connect"
CONNECT_REQUESTED = "Requested"
CONNECT_FELLOWS_LABEL = "You're fellows"
CONNECT_REMOVE = "Remove"
CONNECT_BLOCK = "Block"
CONNECT_UNBLOCK = "Unblock"

# Two-step inline confirms (mirrors the delete-confirm pattern — never a
# naked destructive button).
CONNECT_REMOVE_CONFIRM_BODY = (
    "Remove this fellow connection. This takes away access to each other's full record right away."
)
CONNECT_REMOVE_CONFIRM = "Remove"
CONNECT_REMOVE_CANCEL = "Keep"

CONNECT_BLOCK_CONFIRM_BODY = (
    "Block this account. This also removes any fellow connection or pending request between you."
)
CONNECT_BLOCK_CONFIRM = "Block"
CONNECT_BLOCK_CANCEL = "Cancel"

# Calm inline messages for service exceptions — never a bare 500.
CONNECT_ERROR_ALREADY_EXISTS = "A connection already exists."
CONNECT_ERROR_BLOCKED = "That didn't go through."
CONNECT_ERROR_RATE_LIMITED = "Too many requests for now — try again later."
CONNECT_ERROR_NOT_FOUND = "That request is no longer there."
CONNECT_ERROR_GENERIC = "That didn't go through."

# ---------------------------------------------------------------------------
# People + tag search (Tasks 9-10, social graph)
# ---------------------------------------------------------------------------

SEARCH_TITLE = "Search"
SEARCH_NAV_LABEL = "Search"
SEARCH_BACK_LABEL = "Back"
SEARCH_INPUT_LABEL = "Search people and tags"
SEARCH_INPUT_PLACEHOLDER = "Search by name or tag"
SEARCH_PROMPT = "Search for people by name, or activities by tag."

SEARCH_PEOPLE_HEADING = "People"
SEARCH_PEOPLE_EMPTY = "No one by that name."

SEARCH_TAGS_HEADING = "Tags"
SEARCH_TAGS_EMPTY = "No public records with that tag yet."

# ---------------------------------------------------------------------------
# Entry comments
# ---------------------------------------------------------------------------

# Collapsed per-entry affordance — glyph + count, never shown at zero.
# {count} interpolated by the template.
COMMENTS_COUNT_LABEL = "{count}"
COMMENTS_TOGGLE_ARIA = "Comments"

COMMENTS_EMPTY = "No comments yet."
COMMENTS_LOGIN_TO_COMMENT = "Log in to comment."

COMMENTS_BODY_LABEL = "Add a comment"
COMMENTS_BODY_PLACEHOLDER = "Say something"
COMMENTS_SUBMIT = "Post"
COMMENTS_DELETE = "Delete"

# Quiet, content-free unseen-comment badge on home (mirrors REQUESTS_PENDING_BADGE).
# {count} interpolated by the template.
COMMENTS_UNSEEN_BADGE = "{count}"
COMMENTS_UNSEEN_ARIA = "Unseen comments"

# Dedicated notification-history page (GET /comments) — the only place the
# unseen-comment watermark advances.
COMMENTS_PAGE_TITLE = "Comments"
COMMENTS_PAGE_EMPTY = "No comments yet."
COMMENTS_PAGE_NEW_BADGE_ARIA = "New"
COMMENTS_PAGE_SHOW_OLDER = "Show older"

# ---------------------------------------------------------------------------
# Misc / a11y
# ---------------------------------------------------------------------------

NAV_HOME = "Home"
ALT_LOGO = ""  # decorative
