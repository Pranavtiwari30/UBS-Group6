from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.json import JSON

from payment_exception_mvp.orchestrator import orchestrate


console = Console()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("fixture must contain a JSON object")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Payment Exception MVP orchestrator against one fixture.")
    parser.add_argument("--fixture", required=True, help="Path to a canonical payment exception JSON fixture")
    args = parser.parse_args()

    response = orchestrate(load_json(Path(args.fixture)))
    console.print(JSON.from_data(response))


if __name__ == "__main__":
    main()
