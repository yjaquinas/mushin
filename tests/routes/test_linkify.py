from app.routes.web.common._linkify import linkify


def test_linkify_escapes_text_and_links_http_urls() -> None:
    rendered = str(linkify('<script>x</script> https://example.com/path?tag=one&two=2.'))

    assert "&lt;script&gt;x&lt;/script&gt;" in rendered
    assert 'href="https://example.com/path?tag=one&amp;two=2"' in rendered
    assert ">https://example.com/path?tag=one&amp;two=2</a>." in rendered
    assert 'target="_blank" rel="noopener noreferrer"' in rendered


def test_linkify_adds_https_to_www_urls_and_ignores_non_web_schemes() -> None:
    rendered = str(linkify("www.example.com ftp://example.com"))

    assert 'href="https://www.example.com"' in rendered
    assert "ftp://example.com" in rendered
    assert 'href="ftp://example.com"' not in rendered
