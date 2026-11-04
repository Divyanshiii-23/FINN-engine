"""Portfolio configuration."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from .models import Company

ENGINE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ENGINE_DIR.parent / "data"


class Config(BaseModel):
    companies: list[Company]

    def company(self, symbol: str) -> Company:
        for c in self.companies:
            if c.symbol == symbol:
                return c
        raise KeyError(symbol)


def load(path: Path) -> Config:
    data = yaml.safe_load(path.read_text())
    return Config(companies=[Company(**c) for c in data["companies"]])
