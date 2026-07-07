import json
from pathlib import Path

import pytest

from app.forecasting.registry import ModelRegistry, ModelRegistryError


def test_registry_verifies_shipped_artifact_checksum():
    item = ModelRegistry(Path("data/models/registry.json")).resolve("prematch_classifier")
    assert item["version"] == "demo-trained-v1"
    assert Path(item["path"]).name == "prematch_classifier_demo.json"


def test_registry_rejects_checksum_mismatch(tmp_path):
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "registry.json"
    manifest.write_text(
        json.dumps(
            {
                "models": {
                    "bad": {
                        "version": "1",
                        "artifact": "artifact.json",
                        "checksum": "0" * 64,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ModelRegistryError, match="checksum mismatch"):
        ModelRegistry(manifest).resolve("bad")
