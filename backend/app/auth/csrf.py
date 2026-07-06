"""CSRF double-submit cookie protection.

Strategy:
  A random CSRF token is generated per session and sent to the browser as a
  *non-httpOnly* cookie (name: CSRF_COOKIE_NAME) so JavaScript can read it.
  For every state-changing request (POST/PUT/PATCH/DELETE) authenticated via
  the session cookie, the client must echo the CSRF token in the X-CSRF-Token
  header.  The server compares cookie value == header value using a constant-time
  comparison.

  Bearer/API-key requests are EXEMPT from CSRF checks: they are not cookie-based
  so the cross-site request forgery vector does not apply.

  The CSRF token is tied to the session (stored in the session cookie value's
  namespace); here we derive it by HMAC-ing the session token with a per-token
  salt stored in the session row — but for simplicity in Phase 1 we store a
  separate short-lived CSRF token alongside the session row.  A simpler, equally
  secure approach (used here): generate a random CSRF token on login, store it
  in the UserSession row, and send it as a readable cookie.

Note on SameSite: the session cookie uses SameSite=lax which already blocks most
CSRF for top-level navigations.  The double-submit adds defence-in-depth for
XMLHttpRequest/fetch from the same origin and for older browsers.
"""

import secrets

CSRF_COOKIE_NAME = "pf3d_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"

_TOKEN_BYTES = 32


def generate_csrf_token() -> str:
    """Generate a new random CSRF token."""
    return secrets.token_hex(_TOKEN_BYTES)


def set_csrf_cookie(response, token: str, *, secure: bool) -> None:  # type: ignore[type-arg]
    """Attach the readable CSRF cookie to *response*."""
    from ..models.session import SESSION_LIFETIME_DAYS  # noqa: PLC0415

    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,  # JS must be able to read this
        secure=secure,
        samesite="lax",
        # Must match the session cookie's lifetime: without max_age this is a
        # browser-session cookie, so a browser restart leaves the user logged in
        # (session cookie persists) but unable to pass CSRF on any write.
        max_age=SESSION_LIFETIME_DAYS * 86400,
        path="/",
    )


def clear_csrf_cookie(response) -> None:  # type: ignore[type-arg]
    """Delete the CSRF cookie."""
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/", samesite="lax")


def get_csrf_token_from_cookie(request) -> str | None:  # type: ignore[type-arg]
    """Extract CSRF token from the request cookie."""
    return request.cookies.get(CSRF_COOKIE_NAME)
