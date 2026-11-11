"""Typed unordered query rows; preserve multiplicity, never repair wrong answers."""
from collections import Counter
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import re


def validate_fields(fields):
    if (not isinstance(fields, dict) or not fields or
            any(not isinstance(k, str) or not k or v not in ('string', 'integer', 'decimal')
                for k, v in fields.items())):
        raise ValueError('A record set requires explicit public scalar field types')


def canonical_records(rows, fields):
    validate_fields(fields)
    if not isinstance(rows, list):
        raise ValueError('Records must be an array')
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(fields):
            raise ValueError('Record keys do not match the declared fields')
        values = []
        for key in sorted(fields):
            value, kind = row[key], fields[key]
            if kind == 'string':
                if not isinstance(value, str) or not value.strip():
                    raise ValueError('Record text must be a nonempty string')
                values.append(value.strip())
            else:
                if isinstance(value, bool) or not isinstance(value, (str, int, float)) or not re.fullmatch(r'-?\d+(?:\.\d+)?', str(value)):
                    raise ValueError('Record number must be plain numeric data')
                try:
                    number = Decimal(str(value))
                except InvalidOperation as exc:
                    raise ValueError('Invalid record number') from exc
                if not number.is_finite() or kind == 'integer' and number != number.to_integral_value():
                    raise ValueError('Invalid record numeric type')
                values.append(number)
        result.append(tuple(values))
    return Counter(result)


def record_set_matches(actual, expected, fields):
    reference = canonical_records(expected, fields)  # Invalid oracle is an error.
    try:
        return canonical_records(actual, fields) == reference
    except ValueError:
        return False


def subset_reference(expected, fields, minimum):
    reference=canonical_records(expected,fields)
    if type(minimum)is not int or minimum<1 or len(reference)<minimum or any(n!=1 for n in reference.values()):
        raise ValueError('A subset query requires enough distinct reference records and an explicit minimum')
    return reference


def record_subset_matches(actual,expected,fields,minimum):
    reference=subset_reference(expected,fields,minimum)
    try:answer=canonical_records(actual,fields)
    except ValueError:return False
    return len(answer)>=minimum and all(n==1 and row in reference for row,n in answer.items())


def positive_record_answers(query,values):
    answers={}
    for key,kind in query['fields'].items():
        if kind!='record_subset':continue
        minimum=query.get('minimum_records',{}).get(key)
        subset_reference(values[key],query['record_fields'][key],minimum)
        answer=deepcopy(values);answer[key]=answer[key][:minimum]
        answers[key+'_sufficient_subset']=answer
    return answers


def negative_record_answers(query, values):
    """Private CPU controls: missing, duplicate and wrong rows must never pass."""
    answers = {}
    for key, kind in query['fields'].items():
        if kind not in ('record_set','record_subset'):
            continue
        shape = query['record_fields'][key]
        canonical_records(values[key], shape)
        rows = values[key]
        if kind=='record_subset':
            minimum=query.get('minimum_records',{}).get(key)
            subset_reference(rows,shape,minimum)
        if rows:
            missing = deepcopy(values); missing[key] = missing[key][:minimum-1] if kind=='record_subset' else missing[key][1:]
            duplicate = deepcopy(values); duplicate[key].append(deepcopy(rows[0]))
            wrong = deepcopy(values)
            field = next(iter(shape))
            # Change one field while preserving the declared scalar type.
            if shape[field] == 'string':
                wrong[key][0][field] = 'invalid-control-record-' + rows[0][field]
            else:
                wrong[key][0][field] = str(Decimal(str(rows[0][field])) + 1)
            answers.update({key+'_missing_record': missing, key+'_duplicate_record': duplicate,
                            key+'_wrong_record': wrong})
        else:
            wrong = deepcopy(values)
            wrong[key] = [{field: 'invalid-control-record' if kind == 'string' else 1
                           for field, kind in shape.items()}]
            answers[key+'_unexpected_record'] = wrong
    return answers
