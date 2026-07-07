from __future__ import annotations

import hashlib
import json
from pathlib import Path


class ModelRegistryError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ModelRegistry:
    def __init__(self, manifest_path: Path, *, allow_checksum_mismatch: bool = False) -> None:
        self.manifest_path = manifest_path
        self.allow_checksum_mismatch = allow_checksum_mismatch
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    def resolve(self, name: str) -> dict:
        item = self.manifest.get("models", {}).get(name)
        if not item:
            raise ModelRegistryError(f"model not registered: {name}")
        path = (self.manifest_path.parent / item["artifact"]).resolve()
        if not path.exists():
            raise ModelRegistryError(f"model artifact missing: {path.name}")
        actual = sha256_file(path)
        if actual != item["checksum"] and not self.allow_checksum_mismatch:
            raise ModelRegistryError("model artifact checksum mismatch")
        return {**item, "path": str(path)}
