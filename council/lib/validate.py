"""A small JSON-shape validator — a deliberate subset of JSON Schema.

Supported keywords: type (name or list of names), const, enum, properties,
required, additionalProperties (boolean or schema), items, minItems,
maxItems, pattern (anchored: the whole string must match), minLength,
maxLength, minimum, maximum. Documentation keys ($schema, title,
description, $comment) are ignored.

A schema using any OTHER keyword is refused at load: a schema file must not
promise a constraint this validator does not actually check.
"""

import re

_KEYWORDS = {
    "type", "const", "enum", "properties", "required",
    "additionalProperties", "items", "minItems", "maxItems",
    "pattern", "minLength", "maxLength", "minimum", "maximum",
}
_DOC_KEYS = {"$schema", "title", "description", "$comment"}

_TYPES = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


class SchemaError(ValueError):
    """The schema itself is malformed or uses an unsupported keyword."""


def check_schema(schema, where="$"):
    """Refuse a schema that this validator cannot fully enforce."""
    if not isinstance(schema, dict):
        raise SchemaError("%s: a schema must be an object" % where)
    for key in schema:
        if key not in _KEYWORDS and key not in _DOC_KEYS:
            raise SchemaError("%s: unsupported schema keyword %r" % (where, key))
    declared = schema.get("type")
    if declared is not None:
        names = declared if isinstance(declared, list) else [declared]
        for name in names:
            if name not in _TYPES:
                raise SchemaError("%s: unknown type %r" % (where, name))
    for name, sub in schema.get("properties", {}).items():
        check_schema(sub, "%s.properties.%s" % (where, name))
    if isinstance(schema.get("additionalProperties"), dict):
        check_schema(schema["additionalProperties"],
                     "%s.additionalProperties" % where)
    if "items" in schema:
        check_schema(schema["items"], "%s.items" % where)
    if "pattern" in schema:
        re.compile(schema["pattern"])


def _type_ok(value, names):
    for name in names:
        if name == "integer":
            if isinstance(value, int) and not isinstance(value, bool):
                return True
        elif name == "number":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return True
        elif name == "boolean":
            if isinstance(value, bool):
                return True
        else:
            if isinstance(value, _TYPES[name]) and not (
                    name != "boolean" and isinstance(value, bool)):
                return True
    return False


def validate(instance, schema, path="$"):
    """Return a list of plain-English problems; empty means valid."""
    errors = []

    declared = schema.get("type")
    if declared is not None:
        names = declared if isinstance(declared, list) else [declared]
        if not _type_ok(instance, names):
            errors.append("%s: expected %s, got %s"
                          % (path, " or ".join(names),
                             type(instance).__name__))
            return errors

    if "const" in schema and instance != schema["const"]:
        errors.append("%s: must be exactly %r, got %r"
                      % (path, schema["const"], instance))
    if "enum" in schema and instance not in schema["enum"]:
        errors.append("%s: %r is not one of %s"
                      % (path, instance, schema["enum"]))

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append("%s: shorter than %d characters"
                          % (path, schema["minLength"]))
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append("%s: longer than %d characters"
                          % (path, schema["maxLength"]))
        if "pattern" in schema and not re.fullmatch(schema["pattern"], instance):
            errors.append("%s: %r does not match the required pattern %s"
                          % (path, instance, schema["pattern"]))

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append("%s: %s is below the minimum %s"
                          % (path, instance, schema["minimum"]))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append("%s: %s is above the maximum %s"
                          % (path, instance, schema["maximum"]))

    if isinstance(instance, dict):
        for name in schema.get("required", []):
            if name not in instance:
                errors.append("%s: missing required field %r" % (path, name))
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for name, value in instance.items():
            child = "%s.%s" % (path, name)
            if name in properties:
                errors.extend(validate(value, properties[name], child))
            elif additional is False:
                errors.append("%s: unexpected field %r" % (path, name))
            elif isinstance(additional, dict):
                errors.extend(validate(value, additional, child))

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append("%s: fewer than %d items" % (path, schema["minItems"]))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append("%s: more than %d items" % (path, schema["maxItems"]))
        if "items" in schema:
            for index, value in enumerate(instance):
                errors.extend(validate(value, schema["items"],
                                       "%s[%d]" % (path, index)))

    return errors


def validate_or_raise(instance, schema, label):
    check_schema(schema)
    errors = validate(instance, schema)
    if errors:
        raise ValueError("%s is not valid:\n  %s"
                         % (label, "\n  ".join(errors)))
