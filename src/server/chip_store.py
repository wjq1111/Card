from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CHIPS = 2000


@dataclass(frozen=True)
class ChipAccount:
    player_name: str
    chips: int


class PlayerChipStore:
    def __init__(self, path: str | Path, default_chips: int = DEFAULT_CHIPS) -> None:
        self.path = Path(path)
        self.default_chips = default_chips
        self.lock = threading.RLock()
        self._accounts = self._load()

    def get_or_create(self, player_name: str) -> int:
        normalized = self._normalize_player_name(player_name)
        with self.lock:
            account = self._accounts.get(normalized)
            if account is None:
                account = ChipAccount(player_name=player_name.strip() or "Player", chips=self.default_chips)
                self._accounts[normalized] = account
                self._save()
            return account.chips

    def set_chips(self, player_name: str, chips: int) -> int:
        normalized = self._normalize_player_name(player_name)
        clean_name = player_name.strip() or "Player"
        clean_chips = max(0, int(chips))
        with self.lock:
            self._accounts[normalized] = ChipAccount(player_name=clean_name, chips=clean_chips)
            self._save()
        return clean_chips

    def add_chips(self, player_name: str, amount: int) -> int:
        if amount == 0:
            return self.get_or_create(player_name)
        with self.lock:
            chips = self.get_or_create(player_name)
            return self.set_chips(player_name, chips + amount)

    def _normalize_player_name(self, player_name: str) -> str:
        normalized = player_name.strip()
        if not normalized:
            raise ValueError("Player name is required")
        return normalized.casefold()

    def _load(self) -> dict[str, ChipAccount]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        accounts: dict[str, ChipAccount] = {}
        for normalized_name, payload in data.items():
            accounts[normalized_name] = ChipAccount(
                player_name=str(payload.get("player_name", normalized_name)).strip() or normalized_name,
                chips=max(0, int(payload.get("chips", self.default_chips))),
            )
        return accounts

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            normalized_name: {
                "player_name": account.player_name,
                "chips": account.chips,
            }
            for normalized_name, account in sorted(self._accounts.items())
        }
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)
