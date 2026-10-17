"""Combine frozen AgentTrace datasets into a new, writable local working copy."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sqlite3
import tempfile


def restore(datasets: list[Path], output: Path) -> None:
    if not datasets:
        raise ValueError("At least one dataset is required.")
    if output.exists():
        raise ValueError(f"Refusing to overwrite existing output: {output}")
    for dataset in datasets:
        if not (dataset / "agenttrace.sqlite3").is_file():
            raise ValueError(f"Dataset has no agenttrace.sqlite3: {dataset}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".restore-", dir=output.parent) as temporary:
        staging = Path(temporary) / "results"
        staging.mkdir(mode=0o700)
        with sqlite3.connect(staging / "agenttrace.sqlite3") as destination:
            for index, dataset in enumerate(datasets):
                database = (dataset / "agenttrace.sqlite3").resolve().as_uri() + "?mode=ro"
                with sqlite3.connect(database, uri=True) as source:
                    if source.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                        raise ValueError(f"Invalid snapshot: {dataset}")
                    if index == 0:
                        source.backup(destination)
                    else:
                        with destination:
                            destination.executemany(
                                "INSERT INTO traces (id, content) VALUES (?, ?)",
                                source.execute("SELECT id, content FROM traces"),
                            )
                            destination.executemany(
                                "INSERT INTO runs (id, trace_id, content) VALUES (?, ?, ?)",
                                source.execute("SELECT id, trace_id, content FROM runs"),
                            )
                runs = dataset / "runs"
                if runs.is_dir():
                    for directory in sorted(runs.iterdir()):
                        if directory.is_dir():
                            shutil.copytree(directory, staging / "runs" / directory.name)
            if destination.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Restored analyses reference missing traces.")
        if output.exists():
            raise ValueError(f"Refusing to overwrite existing output: {output}")
        staging.rename(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("datasets", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        restore(args.datasets, args.output)
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.exit(1, f"Restore failed: {error}\n")
    print(f"Saved working copy: {args.output}")


if __name__ == "__main__":
    main()
