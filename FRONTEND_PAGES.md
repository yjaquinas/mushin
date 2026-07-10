# Frontend Page Tree

- **Entry / Login** — `GET /`, `GET /login`
- **Privacy Policy** — `GET /privacy`
- **Terms** — `GET /terms`
- **Profile** — `GET /home`, `GET /@{username}` (owner view)
- **Public Profile** — `GET /@{username}` (non-owner view)
- **Activity Detail** — `GET /activities/{activity_id}`, `GET /@{username}/{slug}`
- **Settings** — `GET /settings`
- **Visibility Update** — `GET /visibility-update`
- **Social** — `GET /social`
- **Comment History** — `GET /comments`
- **Admin Dashboard** — `GET /admin/monitor`, `GET /admin/users`, `GET /admin/users/{user_id}`
