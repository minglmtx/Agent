"""Bounded JSON query response validation; no references or model correction.

Field names and semantic types belong to the public task schema and evaluator.
This transport validator permits its nested values without coercing or repairing
actor output. Finite scalars, nonempty text/objects and empty lists retain their
existing meaning. At the deepest depth only scalar leaves are permitted. The ordinary model
output/token budget is unchanged.
"""
import math

MAX_ANSWER_DEPTH = 8
MAX_ANSWER_NODES = 4096


def normalized_nullable_fields(fields=(), *, answer_fields=None):
    """Only explicit public field names may authorize a top-level JSON null."""
    if (not isinstance(fields, (list, tuple))
            or any(not isinstance(name, str) or not name.strip() for name in fields)
            or len(set(fields)) != len(fields)):
        raise ValueError('Nullable answer fields must be unique nonempty names.')
    if answer_fields is not None and not set(fields).issubset(answer_fields):
        raise ValueError('Nullable fields must be declared requested answer fields.')
    return tuple(fields)


def validate_answer_values(answer, *, nullable_fields=()):
    if not isinstance(answer, dict) or not answer:
        raise ValueError('Query answer must be a nonempty JSON object.')
    nullable_fields = normalized_nullable_fields(nullable_fields, answer_fields=answer)
    nodes = 0

    def visit(value, depth, *, allow_null=False):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_ANSWER_NODES:
            raise ValueError('Query answer exceeds the JSON node budget.')
        if depth > MAX_ANSWER_DEPTH:
            raise ValueError('Query answer exceeds the JSON nesting depth budget.')
        if value is None and allow_null:
            return
        if type(value) is bool:
            return
        if isinstance(value, str):
            if value.strip():
                return
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                if math.isfinite(value):
                    return
            except (OverflowError, TypeError, ValueError):
                pass
        elif isinstance(value, list):
            if depth == MAX_ANSWER_DEPTH:
                raise ValueError('Query answer exceeds the JSON nesting depth budget.')
            for child in value:
                visit(child, depth + 1)
            return
        elif isinstance(value, dict) and value:
            for key, child in value.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError('Query object keys must be nonempty strings.')
                visit(key, depth + 1)
                visit(child, depth + 1, allow_null=depth == 0 and key in nullable_fields)
            return
        raise ValueError('Query values must be nonempty strings, finite numbers, JSON booleans, lists, or nonempty JSON objects.')

    visit(answer, 0)


def bounded_answer_schema(*, nullable_fields=()):
    """The generation schema and parser share the same finite-depth value rules.

    The top-level non-query answer remains a string or number. Query answers
    are nonempty objects. The exact requested keys and semantic field types
    are still checked by ActorProtocol and the independent task evaluator.
    """
    nullable_fields = normalized_nullable_fields(nullable_fields)
    definitions = {}
    for level in range(MAX_ANSWER_DEPTH):
        choices = [
            {'type': 'string', 'minLength': 1},
            {'type': 'number'},
            {'type': 'boolean'},
        ]
        if level > 0:
            child = {'$ref': '#/$defs/query_value_' + str(level - 1)}
            choices += [
                {'type': 'array', 'items': child, 'maxItems': MAX_ANSWER_NODES},
                {'type': 'object', 'minProperties': 1,
                 'propertyNames': {'type': 'string', 'minLength': 1, 'pattern': r'\S'},
                 'additionalProperties': child},
            ]
        definitions['query_value_' + str(level)] = {'anyOf': choices}
    answer = {'anyOf': [
        {'type': 'string', 'minLength': 1},
        {'type': 'number'},
        {'type': 'object', 'minProperties': 1,
         'propertyNames': {'type': 'string', 'minLength': 1, 'pattern': r'\S'},
         'additionalProperties': {'$ref': '#/$defs/query_value_' + str(MAX_ANSWER_DEPTH - 1)}},
    ]}
    if nullable_fields:
        query = answer['anyOf'][2]
        query['properties'] = {
            name: {'anyOf': [dict(query['additionalProperties']), {'type': 'null'}]}
            for name in nullable_fields
        }
    return answer, definitions
