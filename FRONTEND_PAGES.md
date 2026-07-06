# Frontend Page Tree

This inventory is based on the frontend-facing FastAPI routes and their Jinja templates in `app/routes/` and `app/templates/`.

## Naming

- Page names should be user-facing screen names in Title Case, for example `Account Settings`, `Activity Detail`, `Search`, `Comment History`.
- Full-page templates live under `app/templates/web/` or `app/templates/admin/`.
- Routed HTMX fragments live under `app/templates/components/`.
- Include-only partials use an underscore prefix, for example `components/_add_activity_form.html.jinja2`.
- A single page can have more than one endpoint and more than one template if owner/public modes diverge.

## Tree

- Entry / Login
  - Page endpoints
    - `GET /`
    - `GET /login`
  - Page templates
    - `web/comments/entry.html.jinja2` <- `/`, `/login`
  - Routed fragments
    - `components/auth/auth_login_form.html.jinja2` <- `GET /auth/login-form`
    - `components/auth/auth_create_form.html.jinja2` <- `GET /auth/create-form`
  - Include-only templates
    - `components/auth/auth_tabs.html.jinja2`

- Privacy Policy
  - Page endpoints
    - `GET /privacy`
  - Page templates
    - `web/legal/privacy.html.jinja2` <- `/privacy`
  - Include-only templates
    - `web/_privacy_content.html`

- Terms
  - Page endpoints
    - `GET /terms`
  - Page templates
    - `web/legal/terms.html.jinja2` <- `/terms`
  - Include-only templates
    - `web/_terms_content.html`

- Profile
  - Page endpoints
    - `GET /home`
    - `GET /@{username}` when the viewer is the owner
  - Page templates
    - `web/home/profile.html.jinja2` <- `/home`, `/@{username}` owner mode
  - Header actions
    - Share button uses the canonical profile URL when `profile_url` is present.
  - Page-level actions
    - Add Activity button triggers `GET /activities/new` dialog into `#sheet`.
  - Routed fragments
    - `components/activities/activity_sheet.html.jinja2` <- `GET /activities/new` (dialog)
    - `components/activities/activity_form.html.jinja2` <- `POST /activities` on validation error
    - `components/fellows/fellows_section.html.jinja2` <- fellows accept/decline flows on profile:
      - `POST /fellows/requests/{username}/accept`
      - `POST /fellows/requests/{username}/decline`
      - `POST /fellows/requests/{username}/cancel` when used from the fellows section
  - Include-only templates
    - `components/activities/activity_card.html.jinja2`
    - `components/history/stats_summary.html.jinja2`
    - `components/activities/_top_tags_content.html.jinja2`
    - `components/fellows/fellows_section.html.jinja2`
    - `components/fellows/requests_cluster.html.jinja2`

- Settings
  - Page endpoints
    - `GET /settings`
  - Page templates
    - `web/settings/settings.html.jinja2` <- `/settings`
  - Routed fragments
    - `components/common/theme_toggle_settings.html.jinja2` <- `POST /preferences/theme`
    - `components/settings/entry_import_dialog.html.jinja2` <- `POST /import-entries`
  - Related frontend actions without page templates
    - `GET /export-entries`
    - `POST /settings`
    - `POST /settings/email`
    - `POST /delete`
  - Include-only templates
    - `components/settings/delete_account_confirm.html.jinja2`
    - `components/common/theme_toggle_settings.html.jinja2`
    - `components/settings/entry_import_dialog.html.jinja2`

- Visibility Update
  - Page endpoints
    - `GET /visibility-update`
  - Page templates
    - `web/settings/visibility_update.html.jinja2` <- `/visibility-update`
  - Related frontend actions without page templates
    - `POST /visibility-update`

- Social
  - Page endpoints
    - `GET /social`
  - Page templates
    - `web/social/social.html.jinja2` <- `/social`
  - Routed fragments
    - `components/social/explore_results.html.jinja2` <- `GET /social/results`
    - `components/fellows/relationship_affordance.html.jinja2` <- fellows actions when used from search results:
      - `POST /fellows/{username}/connect?source=search`
      - `GET /fellows/requests/{username}/cancel-confirm?source=search`
      - `POST /fellows/requests/{username}/accept?source=search`
      - `POST /fellows/requests/{username}/decline?source=search`
      - `POST /fellows/requests/{username}/cancel?source=search`
      - `GET /fellows/{username}/remove-confirm?source=search`
      - `POST /fellows/{username}/remove?source=search`
      - `GET /fellows/{username}/block-confirm?source=search`
      - `GET /fellows/{username}/block-cancel?source=search`
      - `POST /fellows/{username}/block?source=search`
      - `POST /fellows/{username}/unblock?source=search`
  - Include-only templates
    - `components/social/explore_results.html.jinja2`
    - `components/fellows/relationship_affordance.html.jinja2`
    - `components/_block_link.html.jinja2`

- Comment History
  - Page endpoints
    - `GET /comments`
  - Page templates
    - `web/comments/comments.html.jinja2` <- `/comments`

- Public Profile
  - Page endpoints
    - `GET /@{username}` when the viewer is not the owner
  - Page templates
    - `web/home/public_profile.html.jinja2` <- `/@{username}` public/connected modes
  - Header actions
    - Share button uses the canonical profile URL when `profile_url` is present.
  - Routed fragments
    - `components/fellows/relationship_affordance.html.jinja2` <- fellows relationship actions in profile mode:
      - `POST /fellows/{username}/connect`
      - `GET /fellows/requests/{username}/cancel-confirm`
      - `POST /fellows/requests/{username}/cancel` when used from the relationship affordance
      - `GET /fellows/{username}/remove-confirm`
      - `POST /fellows/{username}/remove`
      - `GET /fellows/{username}/block-confirm`
      - `GET /fellows/{username}/block-cancel`
      - `POST /fellows/{username}/block`
      - `POST /fellows/{username}/unblock`
  - Include-only templates
    - `components/fellows/fellows_section.html.jinja2`
    - `components/fellows/relationship_affordance.html.jinja2`
    - `components/_block_link.html.jinja2`
    - `components/history/stats_summary.html.jinja2`
    - `components/activities/_top_tags_content.html.jinja2`

- Activity Detail
  - Page endpoints
    - `GET /activities/{activity_id}` when the activity is archived or lacks a public slug
    - `GET /@{username}/{slug}` when the viewer is the owner
    - `GET /@{username}/{slug}` when the viewer is an allowed non-owner
  - Page templates
    - `web/activity/detail.html.jinja2` <- `/activities/{activity_id}` archived/no-slug mode, `/@{username}/{slug}` owner mode
    - `web/activity/public_detail.html.jinja2` <- `/@{username}/{slug}` read-only mode
  - Header actions
    - Page title is the username (activity name shown in the summary card).
    - Slugged activity detail pages use the shared profile header with a back link to `/@{username}`.
    - Share button uses the canonical activity URL when `share_url` is present.
    - Archived or no-slug `/activities/{activity_id}` pages do not expose a share action.
  - Routed fragments
    - `components/history/history.html.jinja2` <- `GET /activities/{activity_id}/history`
    - `components/history/stats_summary.html.jinja2` <- `GET /activities/{activity_id}/stats-summary`
    - `components/history/field_stats.html.jinja2` <- `GET /activities/{activity_id}/field-stats`
    - `components/log_sheet.html.jinja2` <- `GET /activities/{activity_id}/log`
    - `components/entries/entry_edit_form.html.jinja2` <- `GET /activities/{activity_id}/entries/{entry_id}/edit`
    - `components/entries/entry_row.html.jinja2` <- `GET /activities/{activity_id}/entries/{entry_id}/cancel-edit`
    - `components/entries/entry_delete_confirm.html.jinja2` <- `GET /activities/{activity_id}/entries/{entry_id}/delete-confirm`
    - `components/rename_form.html.jinja2` <- `GET /activities/{activity_id}/rename-form`
    - `components/rename_form.html.jinja2` <- `POST /activities/{activity_id}/rename` on validation error
    - `components/activities/activity_delete_confirm.html.jinja2` <- `GET /activities/{activity_id}/delete-confirm`
    - `components/comment_thread.html.jinja2` <- `GET /@{username}/{slug}/entries/{entry_id}/comments`
    - `components/comment_thread.html.jinja2` <- `POST /@{username}/{slug}/entries/{entry_id}/comments`
    - `components/comment_delete_confirm.html.jinja2` <- `GET /@{username}/{slug}/entries/{entry_id}/comments/{comment_id}/delete-confirm`
  - Include-only templates
    - `components/history/history.html.jinja2`
    - `components/history/week_strip.html.jinja2`
    - `components/history/period_log.html.jinja2`
    - `components/history/day_entries.html.jinja2`
    - `components/activities/activity_tags.html.jinja2`
    - `components/activities/_top_tags_content.html.jinja2`
    - `components/history/stats_summary.html.jinja2`
    - `components/history/field_stats.html.jinja2`
    - `components/history/competition_stats.html.jinja2`
    - `components/log_sheet.html.jinja2`
    - `components/entries/entry_form_dialog.html.jinja2`
    - `components/entries/_entry_form_fields.html.jinja2`

- Admin Dashboard
  - Page endpoints
    - `GET /admin/monitor`
    - `GET /admin/users`
    - `GET /admin/users/{user_id}`
  - Page templates
    - `admin/dashboard.html.jinja2` <- `/admin/monitor`, `/admin/users`, `/admin/users/{user_id}`
  - Related frontend actions without page templates
    - `GET /admin` redirects to `/admin/monitor`
    - `POST /admin/users/{user_id}/edit`
    - `POST /admin/users/{user_id}/delete`
    - `POST /admin/users/{user_id}/suspension`
    - `POST /admin/users/{user_id}/entries/{entry_id}/edit`
    - `POST /admin/users/{user_id}/entries/{entry_id}/visibility`
    - `POST /admin/users/{user_id}/comments/{comment_id}/edit`
    - `POST /admin/users/{user_id}/comments/{comment_id}/visibility`
  - Include-only templates
    - `components/admin/_admin_nav.html.jinja2`
    - `components/admin/_admin_monitor.html.jinja2`
    - `components/admin/_admin_period_nav.html.jinja2`
    - `components/admin/_admin_selector.html.jinja2`
    - `components/admin/_admin_month_grid.html.jinja2`
    - `components/admin/_admin_recent_visitors.html.jinja2`
    - `components/admin/_admin_recent_content.html.jinja2`
    - `components/admin/_admin_users.html.jinja2`
    - `components/admin/_admin_user_detail.html.jinja2`
    - `components/admin/_admin_user_detail_content.html.jinja2`

## Redirect-Only Or Retired Frontend Endpoints

- `GET /welcome-sharing` and `POST /welcome-sharing` now redirect and do not render a page.
- `web/home/welcome_sharing.html.jinja2` still exists in the template tree, but no current route renders it.

## Quick Rule Of Thumb

- If it is a navigable screen, name it as a page and expect a `web/...` or `admin/...` template.
- If it is an HTMX swap target, name it as a fragment and expect a `components/...` template.
- If it starts with `_`, treat it as an internal partial, not a page or direct fragment endpoint.
