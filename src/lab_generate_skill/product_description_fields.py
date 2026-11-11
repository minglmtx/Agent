"""Read explicit labeled facts from pinned product description HTML."""
import re
from bs4 import BeautifulSoup
from .site_database import select_rows


def clean_table_text(value):
    # Imported product descriptions contain harmless directional formatting marks.
    return re.sub(r'\s+',' ',str(value).translate({ord(c):None for c in '\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff'})).strip()


def labeled_fact(html,label):
    matches=[]
    for row in BeautifulSoup(html,'html.parser').find_all('tr'):
        cells=row.find_all(['td','th'],recursive=False)
        if len(cells)==2 and clean_table_text(cells[0].get_text(' ',strip=True)).rstrip(':').casefold()==label.casefold():
            value=clean_table_text(cells[1].get_text(' ',strip=True))
            if value:matches.append(value)
    if len(matches)!=1:raise ValueError('Description field absent or ambiguous: '+label)
    return matches[0]


def description_fact(site,ident,label):
    if type(ident) is not int or ident<=0 or label not in ('Manufacturer','Material'):raise ValueError('Unsupported product description reference')
    rows=select_rows(site,f"SELECT v.store_id,v.value FROM catalog_product_entity_text v JOIN eav_attribute a ON a.attribute_id=v.attribute_id WHERE v.entity_id={ident} AND a.entity_type_id=4 AND a.attribute_code='description' AND v.store_id IN (0,1) ORDER BY v.store_id")
    effective=[r for r in rows if r['store_id']==1] or [r for r in rows if r['store_id']==0]
    if len(effective)!=1:raise ValueError('Description missing or ambiguous for storefront')
    return labeled_fact(effective[0]['value'],label)
