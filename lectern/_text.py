"""Text helpers kept local so lectern has no non-PyPI dependencies.

``slugify`` is vendored from vaultkit's ``vault_fs`` (the shared vault
primitives package) so the public lectern distribution is self-contained:
``vaultkit`` is private and the name collides with an unrelated PyPI package,
so depending on it would make ``pip install lectern`` pull the wrong code.
Keep this in sync with vaultkit if the slug algorithm ever changes.
"""
from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    collapsed = _NON_ALNUM.sub("-", ascii_text).strip("-")
    if not collapsed:
        raise ValueError(f"cannot slugify: {text!r} produces empty slug")
    return collapsed
