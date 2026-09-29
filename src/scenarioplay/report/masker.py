from __future__ import annotations

MASK = "****"


class Masker:
    """Replaces secret values in every text that leaves the runner (spec section 12).

    Secrets arrive in phase 2; every output already goes through here.
    """

    def __init__(self) -> None:
        self._secrets: set[str] = set()

    def register(self, value: str) -> None:
        if value:
            self._secrets.add(value)

    def __call__(self, text: str) -> str:
        for secret in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(secret, MASK)
        return text
