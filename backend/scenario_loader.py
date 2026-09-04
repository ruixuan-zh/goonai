"""Scenario loading with strict Pydantic validation."""

from __future__ import annotations

import json
from pathlib import Path

from .schemas import Scenario


SCENARIO_DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "scenarios"


def available_scenarios(directory: Path = SCENARIO_DIRECTORY) -> list[str]:
    return sorted(path.stem for path in directory.glob("*.json"))


def load_scenario(name: str, directory: Path = SCENARIO_DIRECTORY) -> Scenario:
    """Load a named scenario without allowing path traversal."""

    if not name or Path(name).name != name or name.endswith(".json"):
        raise ValueError("Scenario name must be a bare filename stem")
    path = directory / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Unknown scenario: {name}")
    return Scenario.model_validate(json.loads(path.read_text(encoding="utf-8")))
