from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

LEGAL_DIR = Path(__file__).resolve().parent.parent / "legal"
FILENAME_RE = re.compile(r"^(?P<code>[a-z_]+)_(?P<version>\d+\.\d+\.\d+)\.md$")


@dataclass(frozen=True, slots=True)
class LegalDocument:
    code: str
    version: str
    title: str
    body: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.body.encode()).hexdigest()


@lru_cache(maxsize=1)
def load_documents() -> tuple[LegalDocument, ...]:
    documents: list[LegalDocument] = []
    for path in sorted(LEGAL_DIR.glob("*.md")):
        match = FILENAME_RE.match(path.name)
        if not match:
            continue
        body = path.read_text(encoding="utf-8").strip()
        title = body.splitlines()[0].lstrip("# ").strip()
        documents.append(
            LegalDocument(
                code=match.group("code"),
                version=match.group("version"),
                title=title,
                body=body,
            )
        )
    return tuple(documents)


def latest_by_code() -> dict[str, LegalDocument]:
    latest: dict[str, LegalDocument] = {}
    for document in load_documents():
        current = latest.get(document.code)
        if current is None or _version_key(document.version) > _version_key(current.version):
            latest[document.code] = document
    return latest


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))
