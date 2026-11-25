"""Small strict JSON-schema subset used by the executable boundary.

Unknown fields, bool-as-integer, NaN and oversized values are rejected. This is
not a general JSON Schema implementation; only the schemas declared here apply.
"""
import math
import re


class SchemaError(ValueError):
    pass


def validate(value, schema, path="$" ):
    kind = schema["type"]
    types = {"object": dict, "array": list, "string": str, "integer": int,
             "number": (int, float), "boolean": bool, "null": type(None)}
    expected = types[kind]
    if not isinstance(value, expected) or (kind in ("integer", "number") and isinstance(value, bool)):
        raise SchemaError(f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaError(f"{path}: unsupported value")
    if kind == "object":
        properties = schema.get("properties", {})
        if set(value) - set(properties):
            raise SchemaError(f"{path}: unknown fields")
        if set(schema.get("required", properties)) - set(value):
            raise SchemaError(f"{path}: missing fields")
        for key, item in value.items():
            validate(item, properties[key], f"{path}.{key}")
    elif kind == "array":
        if len(value) > schema.get("maxItems", 100):
            raise SchemaError(f"{path}: too many items")
        for index, item in enumerate(value):
            validate(item, schema["items"], f"{path}[{index}]")
    elif kind == "string":
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise SchemaError(f"{path}: invalid unicode") from exc
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 10000):
            raise SchemaError(f"{path}: invalid length")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise SchemaError(f"{path}: invalid format")
    elif kind in ("integer", "number"):
        if not math.isfinite(value) or not schema.get("minimum", -math.inf) <= value <= schema.get("maximum", math.inf):
            raise SchemaError(f"{path}: invalid number")
    return value


IDENTIFIER = {"type": "string", "pattern": r"[a-z][a-z0-9_-]{0,63}", "maxLength": 64}
REQUEST_SCHEMA = {
    "type": "object", "properties": {
        "tool": {"type": "string", "minLength": 1, "maxLength": 80},
        "client_id": IDENTIFIER,
        "arguments": {"type": "object", "properties": {}},
    }
}
TOOL_ARGUMENT_SCHEMAS = {
    "overlay.read": {"type": "object", "properties": {"document": {
        "type": "string", "enum": ["facts.json"]}}},
    "draft.prepare": {"type": "object", "properties": {
        "text": {"type": "string", "minLength": 1, "maxLength": 12000}}},
    "delivery.simulate": {"type": "object", "properties": {
        "destination": {"type": "string", "enum": ["synthetic-review-inbox"]},
        "text": {"type": "string", "minLength": 1, "maxLength": 12000}}},
}
OVERLAY_SCHEMA = {
    "type": "object", "properties": {
        "client_id": IDENTIFIER,
        "synthetic": {"type": "boolean", "enum": [True]},
        "brand": {"type": "string", "minLength": 1, "maxLength": 100},
        "approved_facts": {"type": "array", "maxItems": 30, "items": {
            "type": "string", "maxLength": 1000}},
        "canary": {"type": "string", "minLength": 1, "maxLength": 100},
    }
}


def validate_request(request):
    # The outer object is checked before selecting an allowlisted tool schema.
    if type(request) is not dict or set(request) != {"tool", "client_id", "arguments"}:
        raise SchemaError("$: exact tool, client_id and arguments fields required")
    validate(request["tool"], REQUEST_SCHEMA["properties"]["tool"], "$.tool")
    validate(request["client_id"], IDENTIFIER, "$.client_id")
    if request["tool"] not in TOOL_ARGUMENT_SCHEMAS:
        raise SchemaError("$.tool: denied by default")
    validate(request["arguments"], TOOL_ARGUMENT_SCHEMAS[request["tool"]], "$.arguments")
    return request
