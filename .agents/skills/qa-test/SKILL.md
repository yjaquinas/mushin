---
name: qa-test
description: Run QA testing for Mushin user flows using playwright-cli. Tests sign-up, account settings, adding activities, and logging entries. Prints each test before running it and reports pass/fail as it goes. Ends with a summary.
allowed-tools: Bash(playwright-cli:*) Bash(npx:*)
---

# Mushin QA Test Suite

Run every test flow in order. For each test: print what you're about to test, run it, then print PASS or FAIL with a one-line reason.

At the end, print a summary table of all results.

## App URL

`http://localhost:8000`

If the app is not running, stop and tell the user to start the dev server first (`./run.sh` or `uv run uvicorn app.main:app --reload --port 8000`).

## Test credentials

Use a unique test username each run to avoid collisions with existing accounts. Generate it as `qa_<epoch_seconds>` (e.g. `qa_1751000000`). Use password `TestPass123!`.

Get the epoch via:
```bash
date +%s
```

## Test plan (print this before starting)

```
QA Test Suite — Mushin
======================
Test 0: Root page loads
Test 1: Sign up — create account and land on welcome page
Test 2: Account settings — toggle visibility and verify flash confirmation
Test 3a: Adding an activity from empty state (example activity)
Test 3b: Adding a custom activity from empty state (example buttons disappear)
Test 4: Adding an entry — tags, calendar, summary/heatmap
```

---

## IMPORTANT: close any existing browser before starting

```bash
playwright-cli close-all
```

---

## Test 0 — Root page loads

**What to test:** Navigate to `/` and verify the entry screen is shown (not a logged-in home).

Steps:
1. `playwright-cli open http://localhost:8000`
2. Take a snapshot
3. Check the snapshot for the presence of "Create account" or "Log in" text

PASS if: snapshot shows the auth entry screen (login / create account tabs).
FAIL if: snapshot shows a home/dashboard, or an error page.

---

## Test 1 — Sign up

**What to test:** Click "Create account", fill the form, submit, and verify redirect to the welcome-sharing consent page.

Steps:
1. From the root page, find the "Create account" tab and click it
2. Fill in:
   - username: the generated `qa_<epoch>` value
   - password: `TestPass123!`
   - email: leave blank (optional field)
   - consent checkbox: check it
3. Click the submit button
4. Take a snapshot
5. Check that the URL is `/@{username}` or `/welcome-sharing` — either confirms successful signup

PASS if: the page URL is `/@{username}` or `/welcome-sharing`, and the snapshot does not show an auth error.
FAIL if: an error message appears in `[data-auth-error]`, or the URL hasn't changed from `/`.

**Note:** After signup, a new account is redirected to `/welcome-sharing` (first-run visibility consent gate). Submit that form with the default "private" option to proceed to the home page.

If `/welcome-sharing` appears:
1. Find the submit button and click it
2. Verify redirect to `/@{username}` home page

---

## Test 2 — Account settings: toggle visibility

**What to test:** Navigate to `/account`, switch visibility from private to public (or vice versa), save, and confirm the flash message appears without a page redirect.

Steps:
1. Navigate to `http://localhost:8000/account`
2. Take a snapshot — note current visibility selection
3. Select the radio button that is NOT currently checked (flip the current state)
4. Click the Save button
5. Take a snapshot

PASS if: the URL is still `/account` (no redirect), and a flash/confirmation message is visible in the page.
FAIL if: the page redirected away, or no confirmation message is visible.

---

## Test 3a — Add an example activity from empty state

**What to test:** On the home page (`/@{username}`), click one of the example activity buttons to add a pre-filled activity, and verify it appears as a card.

Steps:
1. Navigate to `http://localhost:8000/home`
2. Take a snapshot — verify the empty state is shown (no cards yet)
3. Find one of the example activity buttons (they appear as bordered rows with a small "add" label on the right)
4. Click it
5. Take a snapshot

PASS if: an activity card is now visible in `#cards`, and the empty-state element is gone.
FAIL if: no card appeared, or an error was shown.

---

## Test 3b — Add a custom activity (example buttons disappear)

**What to test:** From the same home page (which now has one card), use the "+ Add activity" button to open the custom form, type a new activity name, submit it, and verify:
- The new activity card appears
- The example activity suggestion buttons are gone (they only show in empty state)

Steps:
1. On the home page, click the "+ Add activity" button (or the equivalent dashed-border button when cards already exist)
2. The inline form (`#add-activity-form`) should become visible
3. Fill the name input (`#category-name`) with `Custom QA Activity`
4. Click the submit button
5. Take a snapshot

PASS if: a card with the name "Custom QA Activity" appears in `#cards`. (Example suggestion buttons would only be present on empty state, so their absence here is expected and correct.)
FAIL if: the form submission failed, the card didn't appear, or an error message was shown.

Note: after this test, the home page has at least 2 cards. Navigate to the custom activity's detail page for Test 4.

---

## Test 4 — Add an entry

**What to test:** Open the detail page for "Custom QA Activity", add an entry for today with a tag (if a tag field exists), and verify:
- The entry appears in the calendar/history section
- The summary stats update (count increments)

Steps:
1. From the home page, find the "Custom QA Activity" card and click on it (or navigate to `/@{username}/{slug}`)
   - The card links to `/@{username}/{slug}` — find the slug from the card's link href using `playwright-cli eval "el => el.href" <card-link-ref>`
2. Take a snapshot of the activity detail page — note the current count in the stats summary
3. Click the Log button (the big "+" / Log button near the top)
4. The `#log-panel` should load inline with a form
5. If a tag group is present, select at least one tag
6. Leave the date as today (it defaults to today)
7. Click the Save / submit button
8. Take a snapshot

PASS if:
- The entry row appears in the history/calendar section
- The stats summary shows an incremented count (or any count ≥ 1)
FAIL if: the form errored, no entry appeared, or the count did not change.

---

## Cleanup

After all tests complete:
1. Navigate to `/account`
2. Click the "Delete account" button (in the Danger zone) to clean up the test user
3. Confirm the deletion dialog
4. Verify redirect to `/`

Then close the browser:
```bash
playwright-cli close
```

---

## Summary format

After all tests, print:

```
QA Summary
==========
Test 0  Root page loads          PASS
Test 1  Sign up                  PASS
Test 2  Account settings         PASS
Test 3a Add example activity     PASS
Test 3b Add custom activity      PASS
Test 4  Add entry                PASS
----------------------------------
6/6 passed
```

Replace PASS/FAIL as appropriate. If any test failed, include a one-line reason next to FAIL.
