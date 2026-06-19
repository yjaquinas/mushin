"""Authentication, accounts, guest mode, sessions, and consent for Mushin.

This package owns everything under the auth boundary: the real providers
(Google, email/password), the anonymous guest account, signed-cookie
sessions, the unbundled consent gate, account/guest deletion, and the
guest upgrade-in-place flow.

Routes live in ``app.auth.routes`` as an ``APIRouter`` registered from
``app.main`` — deliberately *not* in ``app/routes/web.py``, which the web-page
UI task owns separately.
"""

from __future__ import annotations
