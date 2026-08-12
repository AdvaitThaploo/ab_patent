"""Provenance records for pulled data.

Each paid data pull gets a JSON manifest recording the query, timestamp, and
result checksum. The data file and its manifest are both set read-only, so a
write to the same path raises an error instead of silently overwriting data
that was already paid for.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

READ_ONLY = 0o444


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze(path: Path) -> None:
    """Set path to read-only. Callers must unlink before rewriting."""
    path.chmod(READ_ONLY)


def clear(path: Path) -> None:
    """Delete a read-only file and its manifest, so the path can be rewritten."""
    for p in (path, manifest_path(path)):
        p.unlink(missing_ok=True)


def manifest_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".manifest.json")


def write(path: Path, **fields) -> Path:
    """Write a manifest for path and set both files read-only."""
    out = manifest_path(path)
    out.unlink(missing_ok=True)
    out.write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "file": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
                **fields,
                "versions": {
                    p: version(p) for p in ("polars", "google-cloud-bigquery", "google-genai")
                },
            },
            indent=2,
        )
        + "\n"
    )
    freeze(path)
    freeze(out)
    return out
