"""Write SHA-256 hashes for frozen inputs and reproducibility-critical files."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "repository_manifest.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_files() -> list[Path]:
    paths = [
        ROOT / "requirements.txt",
        ROOT / "config" / "project_config.yaml",
    ]
    paths.extend(sorted((ROOT / "data" / "raw").glob("*")))
    paths.extend(sorted((ROOT / "src").glob("*.py")))
    return [path for path in paths if path.is_file()]


def main() -> None:
    rows = []
    for path in tracked_files():
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT, index=False)
    print(f"Saved {len(rows)} manifest rows to {OUTPUT.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
