"""Static validation of tool JSON schemas before they reach Gemini.

Gemini rejects empty enums, missing required keys, and unknown property
references with a 400 INVALID_ARGUMENT. Catching those locally keeps a single
bad tool declaration from breaking every request.
"""

from __future__ import annotations

from typing import Any

VALID_TYPES = {"string", "number", "integer", "boolean", "array", "object"}


def validate_schema(schema: dict[str, Any]) -> list[str]:
    """Return a list of problems with one function-declaration schema."""
    problems: list[str] = []
    name = schema.get("name", "<unnamed>")

    if not name:
        problems.append("declaration has no name")
    if not schema.get("description"):
        problems.append(f"{name}: empty description")

    params = schema.get("parameters") or {"type": "object", "properties": {}}
    if params.get("type") != "object":
        problems.append(f"{name}: parameters must be type=object")
    properties = params.get("properties") or {}

    def check(name_: str, spec: Any, path: str) -> None:
        if not isinstance(spec, dict):
            problems.append(f"{path}: not an object")
            return
        declared = spec.get("type")
        if declared not in VALID_TYPES:
            problems.append(f"{path}: invalid type {declared!r}")
        if not spec.get("description"):
            problems.append(f"{path}: empty description")
        enum = spec.get("enum")
        if enum is not None:
            if not isinstance(enum, list) or not enum:
                problems.append(f"{path}: empty enum")
            else:
                for value in enum:
                    if not isinstance(value, str) or value == "":
                        problems.append(f"{path}: invalid enum value {value!r}")
        if declared == "array":
            items = spec.get("items")
            if not isinstance(items, dict):
                problems.append(f"{path}: array without items")
            else:
                check(f"{path}.items", items, f"{path}.items")
        if declared == "object":
            props = spec.get("properties") or {}
            for key, sub in props.items():
                check(f"{key}", sub, f"{path}.{key}")

    for key, spec in properties.items():
        check(key, spec, f"{name}.{key}")

    for required in params.get("required") or []:
        if required not in properties:
            problems.append(f"{name}: required {required!r} not in properties")

    return problems


def validate_registry(registry: Any) -> tuple[int, list[str]]:
    """Validate every tool; return (checked_count, problems)."""
    problems: list[str] = []
    schemas = registry.get_tool_schemas()
    seen = set()
    for schema in schemas:
        if schema.get("name") in seen:
            problems.append(f"duplicate tool name {schema.get('name')!r}")
        seen.add(schema.get("name"))
        problems.extend(validate_schema(schema))
    return len(schemas), problems


if __name__ == "__main__":
    from jarvis.tools.builtin_tools import build_registry

    count, issues = validate_registry(build_registry())
    print(f"checked {count} tool schemas")
    if issues:
        print(f"{len(issues)} problem(s):")
        for issue in issues:
            print(f"  - {issue}")
        raise SystemExit(1)
    print("all schemas valid")
