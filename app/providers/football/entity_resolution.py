from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


@dataclass(slots=True)
class EntityResolver:
    aliases: dict[tuple[str, str], str] = field(default_factory=dict)

    def resolve(self, provider: str, provider_id: str, display_name: str) -> str | None:
        exact = self.aliases.get((provider, provider_id))
        if exact:
            return exact
        normalized = normalize_name(display_name)
        candidates = {
            canonical for (_, alias), canonical in self.aliases.items() if alias == normalized
        }
        return next(iter(candidates)) if len(candidates) == 1 else None

    def add_reviewed_alias(self, provider: str, provider_id: str, canonical_id: str) -> None:
        self.aliases[(provider, provider_id)] = canonical_id
