"""
Mock CDF Server — FastAPI implementation of the Cognite Data Fusion REST API.

This server mirrors the real CDF REST API endpoint shapes so that the official
cognite-sdk Python client works against it without any code changes. Swapping
this mock for a real CDF tenant requires only changing CDF_BASE_URL and
credentials in the .env file.

IMPORTANT: The cognite-sdk Python client (v7.x) compresses all POST request
bodies using gzip (Content-Encoding: gzip). The GzipRequestMiddleware handles
decompression at the ASGI level before FastAPI sees the body.

Runs on port 4000 (MOCK_CDF_PORT).
"""

import gzip
import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from .routes.assets import router as assets_router
from .routes.timeseries import router as timeseries_router
from .routes.datapoints import router as datapoints_router
from .routes.events import router as events_router
from .routes.relationships import router as relationships_router
from .routes.files import router as files_router
from .store.store import store

PROJECT = "n4798e"
BASE = f"/api/v1/projects/{PROJECT}"


class GzipRequestMiddleware:
    """
    Pure ASGI middleware to decompress gzip-encoded request bodies.

    The cognite-sdk Python client compresses all POST request bodies with gzip
    and sets Content-Encoding: gzip. FastAPI/Starlette does not handle this
    automatically (only gzip response encoding is built-in).

    This middleware unwraps the body before it reaches the route handlers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            raw_headers: list[tuple[bytes, bytes]] = list(scope.get("headers", []))
            is_gzip = any(
                k.lower() == b"content-encoding" and v.lower() == b"gzip"
                for k, v in raw_headers
            )
            if is_gzip:
                # Collect the full body
                chunks: list[bytes] = []
                while True:
                    event = await receive()
                    chunks.append(event.get("body", b""))
                    if not event.get("more_body", False):
                        break
                compressed = b"".join(chunks)
                decompressed = gzip.decompress(compressed)

                # Rebuild headers: remove content-encoding, update content-length
                new_headers = [
                    (k, v) for k, v in raw_headers
                    if k.lower() != b"content-encoding"
                ]
                # Update or add content-length
                new_headers = [
                    (k, str(len(decompressed)).encode() if k.lower() == b"content-length" else v)
                    for k, v in new_headers
                ]
                if not any(k.lower() == b"content-length" for k, _ in new_headers):
                    new_headers.append((b"content-length", str(len(decompressed)).encode()))

                new_scope = dict(scope)
                new_scope["headers"] = new_headers

                body_sent = False

                async def decompressed_receive() -> dict:
                    nonlocal body_sent
                    if not body_sent:
                        body_sent = True
                        return {"type": "http.request", "body": decompressed, "more_body": False}
                    return {"type": "http.disconnect"}

                await self.app(new_scope, decompressed_receive, send)
                return

        await self.app(scope, receive, send)


def create_app() -> FastAPI:
    """Create and configure the FastAPI mock CDF server."""
    _app = FastAPI(
        title="Mock CDF Server",
        description="Cognite Data Fusion REST API mock for aircraft-health-cag-demo",
        version="1.0.0",
    )

    _app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount all CDF resource routers under the CDF project prefix
    _app.include_router(assets_router, prefix=BASE)
    _app.include_router(timeseries_router, prefix=BASE)
    _app.include_router(datapoints_router, prefix=BASE)
    _app.include_router(events_router, prefix=BASE)
    _app.include_router(relationships_router, prefix=BASE)
    _app.include_router(files_router, prefix=BASE)

    # Document download endpoint at root (no project prefix)
    from pathlib import Path  # noqa: PLC0415
    from fastapi.responses import PlainTextResponse  # noqa: PLC0415
    from fastapi import HTTPException  # noqa: PLC0415

    _DOCS_DIR = Path(__file__).parent.parent.parent / "data" / "documents"

    @_app.get("/documents/{filename}", response_class=PlainTextResponse)
    def serve_document_root(filename: str) -> str:
        """Serve document text content from data/documents/."""
        doc_path = _DOCS_DIR / filename
        if not doc_path.exists():
            raise HTTPException(status_code=404, detail=f"Document not found: {filename}")
        return doc_path.read_text()

    @_app.get("/health")
    def health() -> dict[str, Any]:
        """Health check — returns store record counts."""
        counts = store.get_counts()
        return {
            "status": "ok",
            "store": counts,
            "port": int(os.getenv("MOCK_CDF_PORT", "4000")),
        }

    @_app.post("/admin/reload")
    def reload_store() -> dict[str, Any]:
        """Reload the in-memory store from disk — call after ingestion."""
        store.init()
        counts = store.get_counts()
        print(f"[mock-cdf] Store reloaded from disk: {counts}")
        return {"status": "reloaded", "store": counts}

    @_app.post("/admin/set-state")
    def set_demo_state(body: dict[str, Any]) -> dict[str, Any]:
        """
        Switch the active demo state for events and datapoints.

        The three states (clean, caution, grounded) have identical shared history
        up to Nov 1 2025, then diverge into different post-divergence datasets.
        Calling this endpoint switches which state's events/datapoints the mock
        CDF returns — enabling the frontend demo mode selector.
        """
        state = body.get("state", "clean")
        try:
            store.set_state(state)
            counts = store.get_counts()
            print(f"[mock-cdf] Active state switched to: {state} — events: {counts['events']}, datapoints: {counts['datapoints']}")
            return {"status": "ok", "active_state": state, "store": counts}
        except ValueError as e:
            from fastapi import HTTPException  # noqa: PLC0415
            raise HTTPException(status_code=400, detail=str(e))

    @_app.on_event("startup")
    def on_startup() -> None:
        port = os.getenv("MOCK_CDF_PORT", "4000")
        counts = store.get_counts()
        print(f"\n✈  Mock CDF server running on port {port}")
        print(f"   Project: {PROJECT}")
        print(f"   Store: {counts}")
        print(f"   Endpoints: {BASE}/assets, /timeseries, /events, /relationships, /files\n")

    return _app


# Create base FastAPI app, then wrap with ASGI gzip middleware
_base_app = create_app()
app = GzipRequestMiddleware(_base_app)
