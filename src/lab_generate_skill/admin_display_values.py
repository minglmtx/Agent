"""Compare visible Magento representations without dropping identity or precision."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import unescape
import re
from zoneinfo import ZoneInfo


def local_timestamp(value, zone):
    if not zone:raise ValueError('Site timezone missing from state probe')
    return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).astimezone(ZoneInfo(zone)).strftime('%Y-%m-%d %H:%M:%S')


def timestamp_value(value):
    if not isinstance(value,str):raise ValueError('Timestamp must be text')
    value=' '.join(value.split())
    for fmt in ('%Y-%m-%d %H:%M:%S','%Y-%m-%dT%H:%M:%S','%b %d, %Y, %I:%M:%S %p','%B %d, %Y, %I:%M:%S %p'):
        try:return datetime.strptime(value,fmt)
        except ValueError:pass
    raise ValueError('Unsupported timestamp representation')


def row_contains_values(row, reference, numeric_fields):
    text=unescape(row)
    for field,value in reference.items():
        if value is None:continue
        literal=unescape(str(value).strip())
        if field in numeric_fields:
            try:
                number=Decimal(str(value))
                if not number.is_finite():return False
                tokens=re.findall(r'(?<![\w.-])[-+]?\d[\d,]*(?:\.\d+)?(?![\w.-])',text)
                if not any(Decimal(token.replace(',',''))==number for token in tokens):return False
                continue
            except InvalidOperation:return False
        if not re.search(r'(?<!\w)'+re.escape(literal)+r'(?!\w)',text,re.I):return False
    return True
