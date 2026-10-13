"""Nomes das DACs em JSON ({mac: nome}), no computador — não na DAC."""
from __future__ import annotations

import json
import os
import tempfile

from ..application.ports import NameStoreError


class JsonNameStore:
    def __init__(self, path: str, legacy_paths: tuple[str, ...] = ()):
        """legacy_paths: arquivos de nomes do Ether Dream Sitter original, lidos se o nosso ainda não existe.
        O formato é o mesmo."""
        self.path, self.legacy_paths = path, legacy_paths

    def load(self) -> dict[str, str]:
        for path in (self.path,) + self.legacy_paths:
            if os.path.exists(path):
                return self._read(path)
        return {}

    @staticmethod
    def _read(path: str) -> dict[str, str]:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def save(self, names: dict[str, str]) -> None:
        """Grava num temporário e troca: um travamento no meio não corrompe o arquivo."""
        try:
            folder = os.path.dirname(self.path) or "."
            os.makedirs(folder, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(names, fh, ensure_ascii=False, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
        except OSError as e:
            raise NameStoreError(e.strerror or str(e)) from e


class MemoryNameStore:
    def __init__(self, names: dict[str, str] | None = None):
        self.names = dict(names or {})

    def load(self) -> dict[str, str]:
        return dict(self.names)

    def save(self, names: dict[str, str]) -> None:
        self.names = dict(names)
