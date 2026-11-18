"""The API without a server: one ``AppModel`` in memory, every route of the API (routes.py) callable as a function.

Built for Pyodide (GitHub Pages, no backend): standard library only, no threads, no files, no system clock once
the browser supplies ``clientNow``. The browser keeps the document itself with ``export_document`` /
``import_document`` (localStorage, or a file the user downloads and opens again).

    from pathfinder_engine.dispatch import Dispatcher
    d = Dispatcher()
    r = d.handle("POST", "/tick", {}, {"clientNow": "2026-11-05T03:00:00.000Z"})   # {"status": 200, "body": State}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypeVar

from . import metro, routes
from .model import AppModel, ms, parse_iso
from .routes import ROUTES, UNCHANGED, Response
from .seed import SeedFile

T = TypeVar("T")


class MemoryStateStore:
    """The document as the file and blob stores hold it, minus the file: a version counter that every save bumps,
    so ``State.version`` behaves exactly as it does over HTTP."""

    def __init__(self, model: AppModel):
        self.model = model
        if self.model.version == 0:
            self.model.version = 1  # the HTTP stores save the freshly built afternoon once before serving it

    def save(self) -> int:
        self.model.version += 1
        return self.model.version

    def export(self) -> str:
        return json.dumps(self.model.to_dict(), separators=(",", ":"))

    @staticmethod
    def parse(text: str, seed: Optional[SeedFile] = None) -> AppModel:
        try:
            doc = json.loads(text)
        except ValueError as err:
            raise ValueError(f"not a JSON document: {err}") from err
        if not isinstance(doc, dict) or "sim" not in doc or "version" not in doc:
            raise ValueError("not a Pathfinder document: it needs 'sim' and 'version'")
        version = doc.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise ValueError("the document's version must be a whole number")
        return AppModel.from_dict(doc, seed=seed)


class Dispatcher:
    """A ``routes.Session`` over a ``MemoryStateStore``; ``handle`` is the whole API."""

    def __init__(self, seed: Optional[SeedFile] = None, document: Optional[str] = None, now: Optional[str] = None):
        """``now`` (ISO 8601, the browser's clock) dates the fresh afternoon's ``lastTickUtc``, so the first tick
        does not jump; without it the system clock is used until the first ``clientNow`` arrives."""
        self.seed = seed or SeedFile.load()
        self._now: Optional[datetime] = ms(parse_iso(now)) if now else None
        if document:
            model = MemoryStateStore.parse(document, self.seed)
        else:
            model = AppModel(seed=self.seed, warm_up=False, hospital_id=metro.DEFAULT_HOSPITAL)
            model.wall = self.now()
            model.reset()
        self.store = MemoryStateStore(model)

    # The Session protocol

    def read(self) -> AppModel:
        self.store.model.wall = self.now()
        return self.store.model

    def mutate(self, fn: Callable[[AppModel], T]) -> tuple[AppModel, T]:
        m = self.read()
        result = fn(m)
        if result is not UNCHANGED:
            self.store.save()
        return m, result

    def now(self) -> datetime:
        """The browser's clock: the last ``clientNow`` seen (or the ``now`` passed to ``handle``); the system clock
        only until the first tick."""
        return self._now if self._now is not None else ms(datetime.now(timezone.utc))

    def send_text(self, service_url: Optional[str], conversation: Optional[str], text: str,
                  recipient_id: Optional[str]) -> bool:
        return False  # no bot channel without a server

    # The API

    def handle(self, method: str, path: str, query: Optional[dict[str, Any]] = None, body: Optional[dict[str, Any]] = None,
               now: Optional[str] = None) -> Response:
        """One request → ``{"status": int, "body": <json-serialisable>}`` (``"contentType": "text/plain"`` is added
        when the body is text). ``now`` (ISO 8601) or ``body.clientNow`` sets the wall clock for this call and
        the ones after it. ``/api/messages`` and ``/speech/token`` are 404 here: they need a server."""
        stamp = now if now is not None else (body or {}).get("clientNow") if isinstance(body, dict) else None
        if isinstance(stamp, str):
            try:
                self._now = ms(parse_iso(stamp))
            except ValueError:
                pass  # the handler reports the bad timestamp
        return routes.handle(self, method, path, query, body, routes=ROUTES)

    def export_document(self) -> str:
        """The whole document as JSON, for localStorage or a download."""
        return self.store.export()

    def import_document(self, text: str) -> None:
        """Replaces the document with one from ``export_document``; raises ValueError when it is not one."""
        self.store = MemoryStateStore(MemoryStateStore.parse(text, self.seed))
