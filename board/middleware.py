import secrets


def content_security_policy(get_response):
    """Scripts and everything else load only from this site. Styles allow inline attributes (icons, the coverage bar).
    The site has no inline scripts; the nonce is for Cloudflare, which reads it from this header and adds it to the scripts it injects."""

    def middleware(request):
        response = get_response(request)
        nonce = secrets.token_urlsafe(16)
        response.headers.setdefault("Content-Security-Policy", "; ".join((
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        )))
        return response

    return middleware
