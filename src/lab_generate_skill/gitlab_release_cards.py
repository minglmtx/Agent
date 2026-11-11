"""Normalize installed GitLab What's new YAML entries into card references.

The native catalogue calls the heading ``name``. Keep the entire description;
missing or conflicting fields are a reader error, never a fabricated card.
"""


def card_fields(document):
    if not isinstance(document, list) or not document:
        raise ValueError('A nonempty native release entry list is required')
    result = []
    for entry in document:
        if not isinstance(entry, dict):
            raise ValueError('Each native release entry must be an object')
        heading = entry.get('name')
        description = entry.get('description')
        if (not isinstance(heading, str) or not heading.strip()
                or not isinstance(description, str) or not description.strip()):
            raise ValueError('Native name and complete description are required')
        if 'title' in entry and entry['title'] != heading:
            raise ValueError('Conflicting release heading fields')
        result.append({'title': heading, 'description': description})
    if len({r['title'] for r in result}) != len(result):
        raise ValueError('Duplicate native release card names')
    return result
