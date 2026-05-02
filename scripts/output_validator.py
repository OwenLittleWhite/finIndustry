"""Output JSON Schema 校验。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonschema import Draft7Validator  # noqa: E402

SCHEMA_PATH = Path(__file__).parent.parent / "shared_schemas" / "module_output_v1.schema.json"


class ValidationError(ValueError):
    """Wraps jsonschema errors with our own type."""


def validate_output(payload: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        msgs = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors]
        raise ValidationError("module_output_v1 validation failed:\n  " + "\n  ".join(msgs))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    try:
        validate_output(payload)
    except ValidationError as e:
        sys.stderr.write(str(e) + "\n")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
