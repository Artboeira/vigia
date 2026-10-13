"""Versões de firmware conhecidas."""
from __future__ import annotations

import re

# Tabela de ether-dream.com/downloads.html em 2026-10. Atualizar à mão quando sair firmware novo.
LATEST = (("ed4-", 354), ("ed3v", 86), ("r", 331))


def update_available(firmware: str, latest=LATEST) -> str | None:
    """Versão mais nova conhecida se o firmware estiver desatualizado, senão None."""
    for prefix, newest in latest:
        m = re.match(re.escape(prefix) + r"(\d+)", firmware or "")
        if m:
            return "%s%d" % (prefix, newest) if int(m.group(1)) < newest else None
    return None
