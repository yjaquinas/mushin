"""Crawler-facing responses for the public web surface."""

from fastapi.responses import Response


def robots_response() -> Response:
    """Return the authoritative robots policy and production sitemap URL."""
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /privacy\n"
        "Allow: /terms\n"
        "Allow: /licenses\n"
        "Allow: /@*\n"
        "Disallow: /home\n"
        "Disallow: /settings\n"
        "Disallow: /social\n"
        "Disallow: /comments\n"
        "Disallow: /admin\n"
        "Disallow: /auth/\n"
        "Disallow: /welcome-sharing\n"
        "Disallow: /login\n"
        "Disallow: /health\n"
        "\n"
        "Sitemap: https://mushin.aqnas.xyz/sitemap.xml\n"
    )
    return Response(content=content, media_type="text/plain")
