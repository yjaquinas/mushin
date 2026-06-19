---
name: copy-patterns
description: Mushin's English copy voice and string conventions for a US audience — plain, warm, second-person tone, the "Mushin 無心" brand mark (never glossed beyond one line), banned hype language, and the centralized-strings i18n rule. Use whenever writing any user-facing string — onboarding, button labels, empty states, nudges, notifications.
---

# Mushin copy patterns

Mushin is a personal progress tracker — a "raising-sim RPG of yourself." The
brand pairs the English name **Mushin** with the **無心** ("no-mind") hanja as
a quiet mark.

## Register & person

- Plain, warm, second person ("you", "your") — natural American English. Not
  corporate, not hype-driven.
- Frame copy as the user's own record: "your reading log", "today's entry" —
  not a third party narrating at them.

## Tone

- Quietly on the user's side. **Celebrate by stating the fact plainly**
  ("Level 3 reached") and let the number speak. No exclamation spam.
- **No false urgency or guilt.** Banned: "Log now or lose your streak!",
  "Your progress may disappear" — any guilt-trip contradicts the no-mind
  premise.
- **Carve-out: factual data-consequence statements are fine when the user is
  initiating the action themselves** (account-switch confirmation, account
  deletion). State the real consequence neutrally, as fact, never with alarm
  punctuation or framing that implies the user made a mistake.
- XP/level language is quiet structure, never loud decoration.

## Banned register

- Hype-stacked gamer language: "Combo!!", "Mission complete!!", "Level up!! 🔥".
- Exclamation-mark spam and ⚠️-style alarm in normal flows.

## Brand framing (Mushin 無心)

- **Mushin never ships without 無心 beside it** in the masthead and on the
  entry screen — but **never explained**. No "what does 無心 mean?" tooltip or
  etymology aside, anywhere.
- One quiet gloss line on the entry screen and the empty home state:
  *"No-mind. Just show up, and watch it add up."* Don't repeat or expand it
  elsewhere.

## Account-first entry (guest mode retired)

- The entry screen leads with **login / create-account** (a segmented toggle
  over a two-field form: username + password, plus an optional email on create).
  There is no secondary guest path — every user must sign up before logging
  an entry. Username is required; it becomes the public handle in every activity
  URL (`/@{username}/{slug}`).
- The optional email field on create-account is framed as **account
  recovery**, not as a promise of a working password-reset flow — don't say
  "for password reset" until that flow actually ships. Use: *"For account
  recovery. Optional."*
- **`ENTRY_GUEST_LINK` and `ENTRY_GUEST_SUB` are retired strings** — do not
  use them in new templates. They remain in `ui_strings.py` as dead string
  constants until the full guest-cleanup build removes them.
- If a public demo account is configured (`DEMO_PROFILE_USERNAME` env-var), the
  entry screen shows a quiet "See an example record →" link pointing to
  `/@{DEMO_PROFILE_USERNAME}`. This is informational only — copy is factual,
  no sales pressure, no urgency. If the env-var is absent, the link is hidden.

## Theme toggle copy

- Three `aria-label` strings in `ui_strings.py`, one per state, each stating
  current state + the action a tap performs (e.g. "Theme: system. Switch to
  light."). No visible label text — icon + aria-label only.

## i18n

- **Every user-facing string is centralized** in `app/ui_strings.py` — never
  hardcode copy in a template (web or HXML). English at launch; other locales
  are a later addition, not a rewrite — keep the flat, centralized structure.
- Keep layouts width-flexible: labels may run longer if other locales are
  added later — the home hero numeral and "advance" lines must stay flexible
  in that direction.

## Visibility & public profiles

- **The one-time visibility-consent screen** (shown once per account, before
  the owner first reaches `/@{username}`) states plainly, with no alarm framing:
  `public` means your whole record — including your notes — is visible to anyone
  with your profile link; `private` (pre-selected default) means only that your
  page exists, with nothing else shown. This is a factual data-consequence
  statement the user is making themselves — same carve-out as account
  deletion, not a warning. Login, signup, and the consent screen itself all
  send a real (named) user straight to `/@{username}` — there's no
  intermediate redirect. `/home` still renders the activity list in place for
  guests (no `username` to address yet) and, as a fallback, for any real user
  who lands there directly.
- **The private-profile stub** a visitor sees at `/@{username}` for a
  private account is one quiet line — `PROFILE_PRIVATE`: *"This record is
  private."* No lock icons, no "request access" framing (that's a different,
  unbuilt feature).
- **`/account` settings page**: the visibility toggle restates the
  consequence briefly each time it's changed (not the full first-run
  explainer), and the username is framed as the share link — *"Your profile
  is shareable at mushin.aqnas.xyz/@{username}"* — so a user understands
  their login username doubles as a public handle.
- **Rename caption (slug changes on rename).** When the owner edits the activity
  title, a quiet inline caption informs them the shared link will change:
  `RENAME_SLUG_NOTICE`: *"Renaming will change your share link. Anyone with the
  old link will see a 404."* Factual, no alarm punctuation. Shown only when the
  current name already has a slug (i.e. not a brand-new unsaved activity).

## Social-graph vocabulary

- A mutual connection is a **fellow** ("a fellow", "your fellows", "12
  fellows"). Chosen for the *mushin* sense — a peer present to the slow
  adding-up; warmer than "follower", lighter than "friend".
- The action/CTA is always the plain verb **"Connect"** (button, request line).
  Reserve "fellow" for describing the *established* relationship; **never** coin
  a verb ("to fellow someone").
- Connection/consent copy uses the existing calm, factual, no-alarm register
  (mirror `welcome_sharing`): state data consequences plainly ("you'll each see
  the other's full record incl. notes"), no lock icons, no urgency.
- Search empty states: "No one by that name." / "No public records with that
  tag yet." Fellows empty state: "No fellows yet."
- **Supersedes the private-stub copy above:** once the three-tier visibility
  build lands, `private` no longer means "nothing shown" — a visitor sees the
  character sheet. The `PROFILE_PRIVATE` "This record is private." line and the
  "only that your page exists" consent wording get replaced; update the
  "Visibility & public profiles" section above when that ships.
