"""Loopback-only aiohttp gateway for the packaged LiveKit browser client."""

from __future__ import annotations

import argparse
import hmac
import mimetypes
import secrets
import time
from collections import OrderedDict, deque
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web

from .client import LiveKitClient
from .config import BrowserConfig, LiveKitConfig
from .errors import LiveKitError


FRONTEND_ROOT = Path(__file__).with_name("frontend")
AUTH_WINDOW_SECONDS = 60.0
AUTH_FAILURE_LIMIT = 5
MAX_RATE_LIMIT_ADDRESSES = 1024


class FailedAuthLimiter:
    """Bound failed-auth history keyed by the directly connected peer."""

    def __init__(self) -> None:
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()

    def blocked(self, address: str, now: float) -> bool:
        attempts = self._failures.get(address)
        if attempts is None:
            return False
        while attempts and now - attempts[0] >= AUTH_WINDOW_SECONDS:
            attempts.popleft()
        if not attempts:
            self._failures.pop(address, None)
            return False
        self._failures.move_to_end(address)
        return len(attempts) >= AUTH_FAILURE_LIMIT

    def fail(self, address: str, now: float) -> None:
        attempts = self._failures.setdefault(address, deque())
        attempts.append(now)
        self._failures.move_to_end(address)
        while len(self._failures) > MAX_RATE_LIMIT_ADDRESSES:
            self._failures.popitem(last=False)

    def succeed(self, address: str) -> None:
        self._failures.pop(address, None)


def _security_headers(livekit_url: str) -> dict[str, str]:
    parsed = urlsplit(livekit_url)
    websocket_origin = f"{parsed.scheme}://{parsed.netloc}"
    return {
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; media-src 'self' blob:; "
            f"connect-src 'self' {websocket_origin}; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; "
            "frame-ancestors 'none'"
        ),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
    }


def _frontend_files(root: Path) -> dict[str, Path]:
    """Return a fixed URL-to-file map rooted in the packaged frontend."""

    if not (root / "index.html").is_file():
        raise RuntimeError(
            "LiveKit browser assets are missing. Reinstall VoiceMode or run "
            "`make livekit-web-build` from a source checkout."
        )
    return {
        relative.as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
        for relative in (path.relative_to(root),)
    }


def create_app(
    browser_config: BrowserConfig | None = None,
    livekit_config: LiveKitConfig | None = None,
    *,
    frontend_root: Path = FRONTEND_ROOT,
) -> web.Application:
    """Create the gateway application without starting a listener."""

    browser = browser_config or BrowserConfig.from_env()
    livekit = livekit_config or LiveKitConfig.from_env()
    browser_token = browser.require_token()
    livekit.require_credentials()
    files = _frontend_files(frontend_root)
    limiter = FailedAuthLimiter()
    headers = _security_headers(livekit.url)
    expected_host = urlsplit(browser.url).netloc

    @web.middleware
    async def add_security_headers(
        request: web.Request,
        handler: web.RequestHandler,
    ) -> web.StreamResponse:
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            exc.headers.update(headers)
            if request.path == "/api/session":
                exc.headers["Cache-Control"] = "no-store"
            raise
        response.headers.update(headers)
        if request.path == "/api/session":
            response.headers["Cache-Control"] = "no-store"
        return response

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "livekit-web"})

    async def session(request: web.Request) -> web.Response:
        if request.query_string:
            raise web.HTTPBadRequest(text="Query parameters are not accepted.")
        if request.headers.get("Host") != expected_host:
            raise web.HTTPBadRequest(text="Invalid Host header.")
        if request.headers.get("Origin") != browser.origin:
            raise web.HTTPForbidden(text="Invalid Origin header.")

        address = request.remote or "unknown"
        now = time.monotonic()
        if limiter.blocked(address, now):
            raise web.HTTPTooManyRequests(
                text="Too many failed authentication attempts.",
                headers={"Retry-After": str(int(AUTH_WINDOW_SECONDS))},
            )

        authorization = request.headers.get("Authorization", "")
        prefix = "Bearer "
        supplied = authorization[len(prefix) :] if authorization.startswith(prefix) else ""
        if not supplied or not hmac.compare_digest(supplied, browser_token):
            limiter.fail(address, now)
            raise web.HTTPUnauthorized(text="Authentication failed.")
        limiter.succeed(address)

        room_name = f"{livekit.room_prefix}browser-{secrets.token_urlsafe(18)}"
        participant_name = f"voicemode-browser-{secrets.token_urlsafe(18)}"
        try:
            async with LiveKitClient(livekit) as client:
                await client.create_room(room_name)
                token = client.mint_browser_token(
                    room_name,
                    identity=participant_name,
                    display_name="VoiceMode browser",
                )
        except LiveKitError:
            raise web.HTTPBadGateway(
                text="Could not create the VoiceMode room.",
            ) from None

        return web.json_response(
            {
                "serverUrl": livekit.url,
                "roomName": room_name,
                "participantName": participant_name,
                "participantToken": token.token,
            },
            headers={"Cache-Control": "no-store"},
        )

    async def session_method_not_allowed(request: web.Request) -> web.Response:
        raise web.HTTPMethodNotAllowed(request.method, ("POST",))

    async def static_file(request: web.Request) -> web.StreamResponse:
        relative = request.match_info.get("path") or "index.html"
        path = files.get(relative)
        if path is None:
            raise web.HTTPNotFound()
        content_type, _ = mimetypes.guess_type(path.name)
        return web.Response(
            body=path.read_bytes(),
            headers={"Cache-Control": "no-cache"},
            content_type=content_type,
        )

    app = web.Application(middlewares=[add_security_headers])
    app.router.add_get("/health", health)
    app.router.add_post("/api/session", session)
    app.router.add_route("*", "/api/session", session_method_not_allowed)
    app.router.add_get("/", static_file)
    app.router.add_get("/{path:.*}", static_file)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the VoiceMode LiveKit browser")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    browser = BrowserConfig.from_env(host=args.host, port=args.port)
    web.run_app(create_app(browser), host=browser.host, port=browser.port)


if __name__ == "__main__":
    main()
