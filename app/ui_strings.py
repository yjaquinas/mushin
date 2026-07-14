"""Centralized English UI copy for the web renderer.

Every user-facing string in ``app/templates/web/**`` and
``app/templates/components/**`` comes from this module — no hardcoded copy
in templates (grep-checked by
``tests/integration/test_web.py::test_no_hardcoded_copy_in_templates``).

Voice: plain, warm, second person, no hype, no urgency/guilt framing. The
"Mushin 無心" brand mark always ships together and is never explained beyond
the one-line gloss. Position the app as a social network for people who
track — not just a solo logger.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------

APP_NAME = "Mushin"
APP_NAME_HANJA = "無心"

# Error pages
ERROR_PAGE_NOT_FOUND = "The page you're looking for doesn't exist."
ERROR_PAGE_HOME = "Go home"
APP_GLOSS = "No-mind. Just show up, and watch it add up."

# ---------------------------------------------------------------------------
# Entry screen (first run)
# ---------------------------------------------------------------------------

ENTRY_TITLE = "Mushin"
ENTRY_TAGLINE = "Track. Share. Connect."

ENTRY_AUTH_TAB_LOGIN = "Log in"
ENTRY_AUTH_TAB_CREATE = "Create account"

ENTRY_LOGIN_SUBMIT = "Log in"
ENTRY_CREATE_SUBMIT = "Create account"

ENTRY_FIELD_USERNAME = "Username"
ENTRY_FIELD_PASSWORD = "Password"
ENTRY_FIELD_EMAIL = "Email"
ENTRY_FIELD_EMAIL_HELP = "For account recovery. Optional."

ENTRY_CONSENT_CHECKBOX = "I agree to the Privacy Policy"

ENTRY_DEMO_LINK = "See an example record →"

ENTRY_CONSENT_NOTICE = "By creating an account or continuing, you agree to our"
ENTRY_CONSENT_LINK_TEXT = "Privacy Policy"
ENTRY_AUTH_ERROR_DEFAULT_TITLE = "Sign in"
ENTRY_AUTH_ERROR_CLOSE = "Back"

ENTRY_FEED_HEADING = "Recent entries"
ENTRY_FEED_EMPTY = "No public entries yet."
ENTRY_CREATED_AT_LABEL = "created at"

# ---------------------------------------------------------------------------
# Profile (character sheet)
# ---------------------------------------------------------------------------

HOME_TITLE = "Your profile"
HOME_EMPTY = "Nothing started yet."
HOME_ACTIVITIES_HEADING = "Activities"

# One-shot flash confirmation shown after a successful /account/visibility
# save (see app/routes/web.py — the flash cookie is read once, then cleared).
# Carries only the public/private state — no other personal data.
HOME_FLASH_VISIBILITY_PUBLIC = "Profile set to public."
HOME_FLASH_VISIBILITY_PRIVATE = "Profile set to private."
HOME_FLASH_EMAIL_UPDATED = "Email address updated."
HOME_FLASH_PASSWORD_UPDATED = "Password updated."
HOME_FLASH_LOGIN_REQUIRED = "Log in to continue."
ACCOUNT_EMAIL_UPDATE_FAILED = "Could not update email address."

# ---------------------------------------------------------------------------
# Empty-state example activities + create-activity
# ---------------------------------------------------------------------------

HOME_EXAMPLES_HINT = "or try"
HOME_EXAMPLE_ADD = "Add"
HOME_ADD_ACTIVITY = "Add a new activity"

ACTIVITY_NEW_TITLE = "New activity"
ACTIVITY_FORM_NAME_LABEL = "Name"
ACTIVITY_FORM_NAME_PLACEHOLDER = "e.g. Workout (min 2 characters)"
ACTIVITY_FORM_NAME_TOO_SHORT = "Activity name must be at least 2 characters."
ACTIVITY_FORM_SUBMIT = "Create"
ACTIVITY_FORM_CANCEL = "Cancel"
ACTIVITY_FORM_NAME_REQUIRED = "Activity name is required"
ACTIVITY_FORM_NAME_DUPLICATE = "An activity with this name already exists."

ACTIVITY_FORM_SECRET_LABEL = "Secret Activity"
ACTIVITY_FORM_SECRET_HELP = "Only you can see this activity — even your fellows won't see it."
ACTIVITY_SECRET_BADGE = "SECRET"

ACTIVITY_EDIT_TITLE = "Edit activity"
ACTIVITY_EDIT_SAVE = "Save"

# Hero numeral suffixes / labels
HOME_COUNT_UNIT = "times"  # generic running-count unit ("3 times")

SUBTALLY_LOG_BUTTON = "New Entry"
HOME_STREAK_LABEL = "Streak"
HOME_STREAK_DAYS_UNIT = " days"

# ---------------------------------------------------------------------------
# Quick-add / log sheet
# ---------------------------------------------------------------------------

LOG_SUBMIT = "Save entry"
LOG_CANCEL = "Close"

LOG_OCCURRED_AT_LABEL = "Date"
LOG_TIME_LABEL = "Time"
LOG_TIME_NONE = "No time"
LOG_MEMO_LABEL = "Memo"
LOG_MEMO_PLACEHOLDER = "Use #tags to add tags."
LOG_NOTES_MAX_CHARS_REACHED = "Notes can be up to 1000 characters."
LOG_NOTES_MAX_LINES_REACHED = "Notes can be up to 10 lines."

LOG_NOTES_LABEL = "Notes"
LOG_NOTES_PLACEHOLDER = "How'd it go? Add #tags anywhere."

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

# Inline rename form (activity heading)
RENAME_SLUG_NOTICE = "Renaming will change your share link. The old link will stop working."
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
# Competition stats (tournament activities with a match_list field)
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

STATS_PERIOD_WEEK = "This week"
STATS_PERIOD_MONTH = "This month"
STATS_PERIOD_YEAR = "This year"
STATS_PERIOD_LIFETIME = "total"
STATS_AVERAGE_WEEKLY_LABEL = "weekly avg"

STREAK_CURRENT_LABEL = "Current streak"
STREAK_DAY_UNIT = " day"
STREAK_DAYS_UNIT = " days"

CALENDAR_TITLE = "Calendar"
CALENDAR_PREV_MONTH = "Previous month"
CALENDAR_NEXT_MONTH = "Next month"
CALENDAR_WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
CALENDAR_DAY_ENTRIES_TITLE = "Entries on this day"
CALENDAR_DAY_ENTRIES_EMPTY = "No entries on this day."

# Heatmap strip: non-interactive, so HEATMAP_ARIA carries all the
# accessibility information for the whole strip; individual week-bars are
# aria-hidden. {active_weeks} interpolated by the template. Covers the
# current calendar year (fixed-length, future weeks zero-filled) — quarter
# labels (HEATMAP_QUARTER_LABELS) orient the reader within the strip instead
# of a window-length caption.
HEATMAP_ARIA = "Activity this year, {active_weeks} weeks with activity"
HEATMAP_EMPTY = "No entries yet"

# Quarter-start month labels placed along the heatmap strip (sparse — every
# week is a column, but only the week containing a quarter's 1st gets a text
# label, keyed by month number so the template can index directly off a
# bucket's `quarter_month`).
HEATMAP_QUARTER_LABELS = {1: "JAN", 4: "APR", 7: "JUL", 10: "OCT"}

TAGS_HEADING = "Tags"
TAG_FILTER_CLEAR = "All entries"
TAGS_SHOW_ALL = "Show all"
TAGS_SHOW_LESS = "Show less"

# ---------------------------------------------------------------------------
# History: period switcher + actual log
# ---------------------------------------------------------------------------

HISTORY_PERIOD_SWITCHER_LABEL = "Select period"
HISTORY_PERIOD_WEEK = "Week"
HISTORY_PERIOD_MONTH = "Month"
HISTORY_PERIOD_ALL = "All"

HISTORY_WEEK_LABEL = "Week of {date}"
HISTORY_PREV_WEEK = "Previous week"
HISTORY_NEXT_WEEK = "Next week"
HISTORY_TODAY = "Today"

HISTORY_LOG_EMPTY = "Nothing logged in this period."
HISTORY_LOG_EMPTY_TAG = "No entries found for this tag in this period."
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

# Export/import/logout live on the /account page (not the footer) but keep
# their FOOTER_* names — the names predate the move and the copy itself
# isn't footer-specific, so renaming would just duplicate content.
FOOTER_EXPORT_ENTRIES = "Export entries"
FOOTER_IMPORT_ENTRIES = "Import entries"
FOOTER_LOGOUT = "Log out"
FOOTER_DELETE_DATA = "Delete my account"

# Delete-my-data confirm dialog (account page)
DELETE_DATA_TITLE = "Delete all of your data?"
DELETE_DATA_BODY = "This deletes every record kept under this account — activities, entries, etc. This can't be undone."
DELETE_DATA_CONFIRM = "Delete my account"
DELETE_DATA_CANCEL = "Go back"

# Import-data confirm dialog (footer)
IMPORT_DATA_TITLE = "Replace all data with this file?"
IMPORT_DATA_BODY = "This replaces everything currently stored under this account — categories, activities, entries, and memos — with the contents of the uploaded file. This can't be undone."
IMPORT_DATA_FILE_LABEL = "Export file (.json)"
IMPORT_DATA_CONFIRM = "Replace my data"
IMPORT_DATA_CANCEL = "Go back"
IMPORT_DATA_ERROR_TOO_LARGE = "That file is too large to import."
IMPORT_DATA_ERROR_INVALID_FILE = "That doesn't look like a valid export file (.json)."
IMPORT_DATA_ERROR_VALIDATION = "Import failed: {reason}"

# Entry-only import (append-safe, no erase)
IMPORT_ENTRIES_TITLE = "Import entries"
IMPORT_ENTRIES_BODY = "Merge activities and entries from a previous export. Existing data is preserved — duplicates are skipped."
IMPORT_ENTRIES_FILE_LABEL = "Entries file (.json)"
IMPORT_ENTRIES_CONFIRM = "Import entries"
IMPORT_ENTRIES_CANCEL = "Cancel"
IMPORT_ENTRIES_CLOSE = "Close"
IMPORT_ENTRIES_SUCCESS = "Import complete"
IMPORT_ENTRIES_ACTIVITIES_CREATED = "Activities created"
IMPORT_ENTRIES_ENTRIES_IMPORTED = "Entries added"
IMPORT_ENTRIES_ENTRIES_SKIPPED = "Entries skipped (already exist)"
IMPORT_ENTRIES_ERROR_TOO_LARGE = "That file is too large to import."
IMPORT_ENTRIES_ERROR_INVALID_FILE = "That does not look like a valid entries export file (.json)."
IMPORT_ENTRIES_ERROR_VALIDATION = "Import failed: {reason}"

ACCOUNT_PASSWORD_HEADING = "Password"
ACCOUNT_PASSWORD_CURRENT_LABEL = "Current password"
ACCOUNT_PASSWORD_NEW_LABEL = "New password"
ACCOUNT_PASSWORD_UPDATE = "Update password"
ACCOUNT_PASSWORD_INVALID = "Current password is incorrect."
ACCOUNT_PASSWORD_TOO_SHORT = "Password must be at least 8 characters."
ACCOUNT_PASSWORD_WHITESPACE = "Password must not contain whitespace."
ACCOUNT_PASSWORD_SAME = "New password must be different from the current password."
ACCOUNT_PASSWORD_UPDATED = "Password updated."

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
    " who has your profile link."
)

VISIBILITY_CONSENT_PRIVACY_PREFIX = "See our"
VISIBILITY_CONSENT_PRIVACY_LINK_TEXT = "Privacy Policy"
VISIBILITY_CONSENT_PRIVACY_SUFFIX = "for the details."

VISIBILITY_CONSENT_SUBMIT = "Continue"

# ---------------------------------------------------------------------------
# Settings page (/settings) — visibility toggle
# ---------------------------------------------------------------------------

# Same factual, no-alarm register as the consent screen. The toggle restates
# the consequence briefly on each change (not the full first-run explainer).
SETTINGS_TITLE = "Settings"
SETTINGS_DATA_HEADING = "Data"
ACCOUNT_PRIVACY_LINK = "Privacy Policy"
ACCOUNT_TERMS_LINK = "Terms of Service"
ACCOUNT_LICENSES_LINK = "Licenses"

ACCOUNT_VISIBILITY_HEADING = "Account"
ACCOUNT_SHARE = "Share"
ACCOUNT_SHARE_COPIED = "Profile link copied."
ACCOUNT_SHARE_FAILED = "Couldn't share the profile link."

# Radio labels mirror the consent screen.
ACCOUNT_VISIBILITY_PRIVATE_LABEL = "Private"
ACCOUNT_VISIBILITY_CURRENT_BADGE = "Current saved value"
ACCOUNT_VISIBILITY_PRIVATE_TAGLINE = "Only visible to you and your fellows."
ACCOUNT_VISIBILITY_PRIVATE_DESC = (
    "Visitors see your activity names and counts, but not your entries"
    " or notes. Fellows you connect with see everything."
)
ACCOUNT_VISIBILITY_PUBLIC_LABEL = "Public"
ACCOUNT_VISIBILITY_PUBLIC_TAGLINE = "Visible to anyone with your profile link."
ACCOUNT_VISIBILITY_PUBLIC_DESC = (
    "Your whole record — every activity, entry, and note — is visible to anyone"
    " who has your profile link."
)

ACCOUNT_VISIBILITY_SAVE = "Save"
ACCOUNT_EMAIL_HEADING = "Email address"
ACCOUNT_EMAIL_LABEL = "Recovery email"
ACCOUNT_EMAIL_HELP = "For account recovery. Optional."
ACCOUNT_EMAIL_UPDATE = "Update email"
ACCOUNT_EMAIL_INVALID = "Enter a valid email address."
ACCOUNT_EMAIL_TAKEN = "That email address is already in use."

HOME_FLASH_BIO_UPDATED = "Bio updated."

SETTINGS_THEME_HEADING = "Theme"

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
# Legal pages (privacy, terms, licenses) + shared dialog string
# ---------------------------------------------------------------------------
PRIVACY_PAGE_TITLE = "Privacy Policy"

TERMS_PAGE_TITLE = "Terms of Service"

LICENSES_PAGE_TITLE = "Open Source Licenses"
LEGAL_DIALOG_CLOSE = "Close dialog"

# ---------------------------------------------------------------------------
# Public profiles (/@{username}, /@{username}/{slug})
# ---------------------------------------------------------------------------

PROFILE_BIO_HEADING = "About me"
PROFILE_BIO_PLACEHOLDER = "Write a short bio. Max 100 characters."
PROFILE_BIO_HEADING_SOCIAL = "About {username}"
PROFILE_BIO_EMPTY = "Write a short bio."
PROFILE_BIO_EDIT = "Edit bio"
PROFILE_BIO_SAVE = "Save"
PROFILE_BIO_CANCEL = "Cancel"
PROFILE_BIO_TOO_LONG = "Bio must be 100 characters or fewer."

PROFILE_ACTIVITIES_EMPTY = "No activities logged yet."

# Quiet line above the character-sheet (limited) view of a private account.
PROFILE_LIMITED_NOTICE = "{username} is a private user. Connect to see more."

# Owner-view notice on a public activity page — factual, no alarm framing.
ACTIVITY_PUBLIC_NOTICE = "This page is public — anyone with the link sees it, notes included."

PROFILE_VISIT = "{username}'s profile"
ACTIVITY_BACK_TO_PROFILE = "Back to profile"

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
ENTRY_HIDDEN_BY_MODERATOR = "Hidden by moderator"

# ---------------------------------------------------------------------------
# Fellows + requests (social graph, Task 6)
# ---------------------------------------------------------------------------

FELLOWS_HEADING = "Fellows"
HOME_FLASH_FELLOWS_PRIVATE = "This profile is private."
TOAST_DISMISS = "Dismiss"

# ---------------------------------------------------------------------------
# PWA install banner
# ---------------------------------------------------------------------------

PWA_INSTALL_TEXT = "Install Mushin for quick access from your home screen."
PWA_INSTALL_BUTTON = "Install"
PWA_INSTALL_DISMISS = "Not now"
PWA_INSTALL_SAFARI_IOS_TEXT = "Install Mushin for quick access. Share, View More, then Add to Home Screen."
PWA_INSTALL_SAFARI_MAC_TEXT = "Install Mushin for quick access. Share, then Add to Dock."

# {count} interpolated by the template. Used for non-owner/non-fellow
# viewers, who see only the number, never the clickable names.
FELLOWS_COUNT_LABEL = "{count} fellows"
FELLOWS_COUNT_LABEL_ONE = "1 fellow"
FELLOWS_EMPTY = "No fellows yet."
FELLOWS_MANAGE = "See all"
FELLOWS_FELLOW_LABEL = "Fellow"

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
CONNECT_REMOVE = "Remove"
CONNECT_BLOCK = "Block"
CONNECT_UNBLOCK = "Unblock"
CONNECT_CANCEL_REQUEST = "Cancel request"

# Two-step inline confirms (mirrors the delete-confirm pattern — never a
# naked destructive button).
CONNECT_REMOVE_CONFIRM_BODY = (
    "Remove this fellow connection. This takes away access to each other's full record right away."
)
CONNECT_REMOVE_CONFIRM = "Remove"
CONNECT_REMOVE_CANCEL = "Keep"
CONNECT_CANCEL_REQUEST_CONFIRM_BODY = "Cancel this pending connection request?"
CONNECT_CANCEL_REQUEST_CONFIRM = "Cancel request"
CONNECT_CANCEL_REQUEST_KEEP = "Keep request"

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
# People, tag, and activity search
# ---------------------------------------------------------------------------

SOCIAL_TITLE = "Social"
SOCIAL_FEED_HEADING = "Recently updated activities"
SEARCH_OPEN_ARIA = "Open search"
SEARCH_CLOSE_ARIA = "Close search"
SEARCH_INPUT_LABEL = "Search people, tags, or activities"
SEARCH_INPUT_PLACEHOLDER = "Search people, tags, or activities"
SEARCH_PROMPT = "Type to search across people, tags, and activities. Use @ for people or # for tags to narrow results."
SEARCH_ALL_EMPTY = "No results found."

SEARCH_PEOPLE_HEADING = "People"
SEARCH_PEOPLE_EMPTY = "No one by that name."

SEARCH_TAGS_HEADING = "Tags"
SEARCH_TAGS_EMPTY = "No visible records with that tag yet."
SEARCH_TAG_COUNT = "{count} uses"

SEARCH_ACTIVITIES_HEADING = "Activities"
SEARCH_ACTIVITIES_EMPTY = "No activities by that name."
SEARCH_ACTIVITY_COUNT = "{count} times"

# ---------------------------------------------------------------------------
# Entry comments
# ---------------------------------------------------------------------------

# Collapsed per-entry affordance — glyph + count, never shown at zero.
# {count} interpolated by the template.
COMMENTS_COUNT_LABEL = "{count}"
COMMENTS_TOGGLE_ARIA = "Comments"
COMMENTS_CLOSE = "Close comments"

COMMENTS_EMPTY = "No comments yet."
COMMENTS_LOGIN_TO_COMMENT = "Log in to comment."

COMMENTS_BODY_LABEL = "Add a comment"
COMMENTS_BODY_PLACEHOLDER = "Say something"
COMMENTS_SUBMIT = "Post"
COMMENTS_BODY_MAX_CHARS_REACHED = "Comments can be up to 200 characters."
COMMENTS_BODY_MAX_LINES_REACHED = "Comments can be up to 5 lines."
COMMENTS_DELETE = "Delete"
COMMENTS_DELETE_CONFIRM_BODY = "Delete this comment. This can't be undone."
COMMENTS_DELETE_CONFIRM = "Delete"
COMMENTS_DELETE_CANCEL = "Keep"
COMMENTS_HIDDEN_BY_MODERATOR = "Hidden by moderator"
COMMENTS_AUTHOR_OWNER = "Owner"
COMMENTS_AUTHOR_YOU = "You"

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
# Bottom navigation bar
# ---------------------------------------------------------------------------

NAV_PROFILE = "Profile"
NAV_SOCIAL = "Social"
NAV_SETTINGS = "Settings"
NAV_APP = "App navigation"

# ---------------------------------------------------------------------------
# Admin (operator dashboard, HTTP Basic Auth gated)
# ---------------------------------------------------------------------------

ADMIN_DASHBOARD_TITLE = "Mushin Admin Dashboard"
ADMIN_NAV_MONITOR = "Monitor"
ADMIN_NAV_USERS = "Users"
ADMIN_VISITOR_HEADING = "Visitors"
ADMIN_VISITOR_NOTE = (
    "Visitors are deduplicated by IP, device details, and language within a two-hour window. "
    "Sources come from the browser's referrer header; browser history is not available."
)
ADMIN_VISITOR_TODAY = "Today"
ADMIN_VISITOR_WEEK = "Last 7 days"
ADMIN_VISITOR_MONTH = "Last 30 days"
ADMIN_COUNTRIES_HEADING = "Countries"
ADMIN_REFERRERS_HEADING = "Sources"
ADMIN_RECENT_VISITORS_HEADING = "Recent visitors"
ADMIN_RECENT_EMPTY = "No visitor records yet."
ADMIN_PERIOD_HEADING = "Monitoring"
ADMIN_PERIOD_CURRENT = "Selected period"
ADMIN_PERIOD_DAILY = "Daily"
ADMIN_PERIOD_WEEKLY = "Weekly"
ADMIN_PERIOD_MONTHLY = "Monthly"
ADMIN_PERIOD_YEARLY = "Yearly"
ADMIN_PREVIOUS_YEAR = "Previous year"
ADMIN_NEXT_YEAR = "Next year"
ADMIN_PREVIOUS_PAGE = "Previous page"
ADMIN_NEXT_PAGE = "Next page"
ADMIN_PAGE_LABEL = "Page {page} of {total}"
ADMIN_COLUMN_TIME = "Time"
ADMIN_COLUMN_LOCATION = "Location"
ADMIN_COLUMN_DEVICE = "Device"
ADMIN_COLUMN_SOURCE = "Source"
ADMIN_COLUMN_PATH = "Path"
ADMIN_UNKNOWN = "Unknown"
ADMIN_DIRECT_UNKNOWN = "Direct / unknown"
ADMIN_NOT_TRACKED = "Not tracked yet"
ADMIN_EMPTY_FIELD = "None"
ADMIN_VIEW_LINK = "View"
ADMIN_MANAGEMENT_PENDING = "Management service pending"
ADMIN_MANAGEMENT_NOTE = (
    "Suspend, edit, and hide controls need moderation enforcement in the service layer before "
    "they can safely change data."
)
ADMIN_MANAGEMENT_ACTIVE_NOTE = (
    "These actions write reversible moderation state. Hidden entries and comments are excluded "
    "from normal user-facing reads."
)
ADMIN_MANAGEMENT_HEADING = "Management"
ADMIN_BACK_TO_USERS = "Back to users"
ADMIN_PUBLIC_PROFILE = "Public profile"
ADMIN_EDIT_USER_HEADING = "Edit user"
ADMIN_FIELD_USERNAME = "Username"
ADMIN_FIELD_EMAIL = "Email"
ADMIN_FIELD_PASSWORD = "New password"
ADMIN_SAVE_USER = "Save user"
ADMIN_SAVE = "Save"
ADMIN_SUSPEND_USER = "Suspend user"
ADMIN_UNSUSPEND_USER = "Unsuspend user"
ADMIN_HIDE = "Hide"
ADMIN_UNHIDE = "Unhide"
ADMIN_STATUS_SUSPENDED = "Suspended"
ADMIN_STATUS_HIDDEN = "Hidden"
ADMIN_STATUS_ACTIVE = "Active"
ADMIN_STATUS_DELETED = "Deleted"
ADMIN_RECENT_CONTENT_HEADING = "Recent content"
ADMIN_RECENT_ACTIVITIES_HEADING = "Recently added activities"
ADMIN_RECENT_ENTRIES_HEADING = "Recently added entries"
ADMIN_RECENT_COMMENTS_HEADING = "Recently added comments"
ADMIN_USERS_HEADING = "Users"
ADMIN_USERS_NOTE = "Select a username to open that user's admin detail page."
ADMIN_DELETED_USERS_NOTE = "Deleted accounts keep their history, but account access and original usernames are removed."
ADMIN_DELETED_ACCOUNT_NOTE = "Account access has been deleted. History remains available for admin review."
ADMIN_USER_TRACKING_HEADING = "Common user dashboard tracking"
ADMIN_USER_TRACKING_STATUS = "Account status and moderation state"
ADMIN_USER_TRACKING_AUTH_VISIT = "Last authenticated visit"
ADMIN_USER_TRACKING_VISIT_COUNT = "Total authenticated visit count"
ADMIN_USER_TRACKING_DEVICE = "Last device, browser, and operating system"
ADMIN_USER_TRACKING_LOCATION = "Last IP country or region"
ADMIN_USER_TRACKING_CONTENT = "Activity, entry, and comment totals"
ADMIN_USER_TRACKING_MODERATION = "Hidden content, reports, and suspension history"
ADMIN_COLUMN_USER = "User"
ADMIN_COLUMN_USERNAME = "Username"
ADMIN_COLUMN_ACCOUNT_STATUS = "Account status"
ADMIN_COLUMN_CREATED = "Created"
ADMIN_COLUMN_LAST_VISITED = "Last visited"
ADMIN_COLUMN_VISITS = "Visits"
ADMIN_COLUMN_ACTIVITIES = "Activities"
ADMIN_COLUMN_ENTRIES = "Entries"
ADMIN_COLUMN_COMMENTS = "Comments"
ADMIN_COLUMN_MANAGEMENT = "Management"
ADMIN_COLUMN_ACTIVITY = "Activity"
ADMIN_COLUMN_NAME = "Name"
ADMIN_COLUMN_NOTES = "Notes"
ADMIN_COLUMN_ENTRY_USER = "Entry user"
ADMIN_COLUMN_COMMENT_USER = "Comment user"
ADMIN_COLUMN_TEXT = "Text"

# ── Admin: user email & delete ──────────────────────────────────────

ADMIN_VISIBILITY_HEADING = "Visibility"
ADMIN_VISIBILITY_PUBLIC = "Public"
ADMIN_VISIBILITY_PRIVATE = "Private"
ADMIN_VISIBILITY_CURRENT = "Current: {visibility}"
ADMIN_SET_VISIBILITY = "Set visibility"

ADMIN_COLUMN_EMAIL = "Email"
ADMIN_DELETE_USER_HEADING = "Delete user"
ADMIN_DELETE_USER_BODY = (
    "Permanently remove this user's account access and username. "
    "Their entries and comments will remain but be unattributed."
)
ADMIN_DELETE_USER_CONFIRM = "Delete user"
ADMIN_DELETE_USER_CANCEL = "Cancel"

# ---------------------------------------------------------------------------
# SEO / Metadata
# ---------------------------------------------------------------------------

META_TITLE_INDEX = "Mushin 無心 — Track. Share. Connect."
META_DESCRIPTION_INDEX = (
    "A social network for people who track. Log activities, share your "
    "journey, and connect with others who show up."
)
META_DESCRIPTION_PROFILE = (
    "{username}'s profile on Mushin — a social network for tracking "
    "progress and connecting with others."
)
META_DESCRIPTION_ACTIVITY = (
    "{activity} by {username} on Mushin — a social network for tracking "
    "progress and connecting with others."
)
OG_IMAGE_URL = "/static/img/og-default.png"
META_DESCRIPTION_PRIVACY = "Privacy Policy for Mushin 無心 — how your data is handled on this social progress tracker."
META_DESCRIPTION_TERMS = "Terms of Service for Mushin 無心 — the rules for using this social progress tracker."
META_DESCRIPTION_LICENSES = "Open source licenses used by Mushin 無心."

# ---------------------------------------------------------------------------
# Plans & upgrade
# ---------------------------------------------------------------------------

PLANS_PAGE_TITLE = "Plans"
PLANS_HEADING = "Choose your plan"
PLANS_SUBHEADING = "Unlock more activities, entries, and features as your tracking grows."
PLANS_BASIC_NAME = "Basic"
PLANS_PREMIUM_NAME = "Premium"
PLANS_FREE = "Free"
PLANS_PER_MONTH = "/ month"
PLANS_GET_STARTED = "Get started"
PLANS_COMING_SOON = "Coming soon"
PLANS_FEATURE_ACTIVITIES = "{count} activities"
PLANS_FEATURE_ENTRIES = "{count} entries per date"
PLANS_FEATURE_SECRET = "Secret activities"

ACTIVITY_LIMIT_TOAST = "Basic plan: {max} activities. Premium includes {premium_max}."
ENTRY_DATE_LIMIT_TOAST = "Basic plan: {max} entry per day. Premium allows {premium_max}."
SECRET_ACTIVITY_TOAST = "Secret activities are available on the Premium plan."

# Plans page (inside settings)
PLANS_BACK_TO_SETTINGS = "Back to settings"
PLANS_CURRENT_PLAN_STRONG = "Your current plan"

# Settings — plan section
SETTINGS_PLAN_HEADING = "Plan"
SETTINGS_PLAN_ACTIVITIES_USED = "{used} / {max} activities in use"
SETTINGS_PLAN_CURRENT_LABEL = "Current plan"
SETTINGS_PLAN_VIEW_BUTTON = "View plans"
SETTINGS_PLAN_NEXT_BILLING = "Next billing: {date}"
SETTINGS_PLAN_PAYMENT_HISTORY = "Payment history"
SETTINGS_PLAN_PAYMENT_COUNT = "Payment history ({count})"
SETTINGS_PLAN_PAYMENT_EMPTY = "No payment records yet."

# Admin — plans
ADMIN_NAV_PLANS = "Plans"
ADMIN_PLANS_HEADING = "Plans"
ADMIN_PLANS_NOTE = "Configure plan limits and pricing. Changes take effect immediately."
ADMIN_PLAN_NAME = "Name"
ADMIN_PLAN_MAX_ACTIVITIES = "Max activities"
ADMIN_PLAN_MAX_ENTRIES = "Max entries per date"
ADMIN_PLAN_SECRET = "Secret activities"
ADMIN_PLAN_PRICE_MONTHLY = "Price (monthly, cents)"
ADMIN_PLAN_PRICE_YEARLY = "Price (yearly, cents)"
ADMIN_PLAN_SAVE = "Save"
ADMIN_PLAN_SAVED = "Plan settings saved."
ADMIN_PLAN_ERROR_INVALID = "Plan settings could not be saved."
ADMIN_PLAN_COLUMN_PLAN = "Plan"
ADMIN_PLAN_COLUMN_LIMITS = "Limits"
ADMIN_PLAN_COLUMN_PRICING = "Pricing"

# Admin — user plan
ADMIN_USER_PLAN_HEADING = "Plan"
ADMIN_USER_PLAN_LABEL = "Current plan"
ADMIN_USER_PLAN_SET = "Set plan"
ADMIN_USER_PLAN_CHANGED = "Plan changed."
ADMIN_USER_PLAN_PROMOTION = "Give promotion"
ADMIN_USER_PLAN_PROMOTION_GIVEN = "Premium promotion granted."
ADMIN_USER_PLAN_MONTHS_LABEL = "months"

# Admin — payment history
ADMIN_PAYMENTS_HEADING = "Payment History"
ADMIN_PAYMENTS_EMPTY = "No payment records yet."
ADMIN_PAYMENTS_COLUMN_DATE = "Date"
ADMIN_PAYMENTS_COLUMN_PLAN = "Plan"
ADMIN_PAYMENTS_COLUMN_AMOUNT = "Amount"
ADMIN_PAYMENTS_COLUMN_STATUS = "Status"
ADMIN_PAYMENTS_COLUMN_METHOD = "Method"
ADMIN_PAYMENTS_COLUMN_PERIOD = "Period"
