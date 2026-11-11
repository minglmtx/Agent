"""Snapshot-backed Reddit query references and independent native UI readers."""
import re
from datetime import datetime
from urllib.parse import urlsplit, unquote
from zoneinfo import ZoneInfo
from .site_database import select_rows


def one(rows):
    if len(rows) != 1: raise ValueError('Reference missing or ambiguous')
    return rows[0]


def integer(value):
    if type(value) is not int or value <= 0: raise ValueError('Invalid object ID')
    return value


def date_in_zone(timestamp, zone):
    dt = datetime.fromisoformat(timestamp)
    if dt.tzinfo is None: raise ValueError('Timestamp has no timezone')
    return dt.astimezone(ZoneInfo(zone)).date().isoformat()


def displayed_date(title):
    # Parse only the native English date prefix, independently of datetime/DB.
    m = re.match(r'^([A-Za-z]+ \d{1,2}, \d{4})(?: at |$)', title or '')
    if not m: raise ValueError('Native absolute date unavailable')
    return datetime.strptime(m[1], '%B %d, %Y').date().isoformat()


def count_label(text, noun):
    if text.strip().casefold() == 'no '+noun+'s': return 0
    m = re.fullmatch(r'([\d,]+) '+re.escape(noun)+r's?', text.strip())
    if not m: raise ValueError('Native count label unavailable')
    return int(m[1].replace(',', ''))


def post_record(site, ident):
    return one(select_rows(site, f'SELECT s.id,s.title,s.timestamp,s.comment_count,s.net_score,s.visibility,f.name AS forum,u.username FROM submissions s JOIN forums f ON f.id=s.forum_id JOIN users u ON u.id=s.user_id WHERE s.id={integer(ident)}'))


def forum_prefix(q):
    prefix=q.get('name_prefix')
    if (not isinstance(prefix,str) or not re.fullmatch('[A-Za-z]',prefix) or
            q.get('fields')!={'items':'record_set'} or
            q.get('record_fields')!={'items':{'name':'string'}}):
        raise ValueError('Unsupported forum-name query scope or output fields')
    return prefix.casefold()


def reference(site, q):
    ident = integer(q['object_id']); family = q['family']; values = {}
    if family=='reddit_forum_names':
        prefix=forum_prefix(q)
        rows=select_rows(site,'SELECT id,name FROM forums ORDER BY id')
        if len({r['name'] for r in rows})!=len(rows):raise ValueError('Ambiguous native forum names')
        return {'object_id':family+':'+str(ident),
                'values':{'items':[{'name':r['name']} for r in rows if r['name'].casefold().startswith(prefix)]},
                'source_state':rows}
    if family == 'reddit_post':
        row = post_record(site, ident)
        if row['title'] != q['object_name'] or row['forum'] != q['forum'] or row['visibility'] != 'visible':
            raise ValueError('Post identity or visibility changed')
        if 'submission_date' in q['fields']:
            viewer = one(select_rows(site, f"SELECT timezone FROM users WHERE id={integer(q['viewer_id'])}"))
        for field in q['fields']:
            if field == 'submission_date': value = date_in_zone(row['timestamp'], viewer['timezone'])
            elif field == 'author': value = row['username']
            elif field in ('comment_count', 'title', 'net_score'): value = row[field]
            else: raise ValueError('Unsupported Reddit post field')
            values[field] = value
    elif family == 'reddit_account':
        row = one(select_rows(site, f'SELECT username,created,timezone,trusted FROM users WHERE id={ident}'))
        if row['username'] != q['username']: raise ValueError('Wrong account identity')
        for field in q['fields']:
            if field == 'registration_date': value = date_in_zone(row['created'], row['timezone'])
            # Whitelisting equals trusted in this pinned Postmill source (verified separately).
            elif field == 'whitelisted': value = 'yes' if row['trusted'] else 'no'
            else: raise ValueError('Unsupported Reddit account field')
            values[field] = value
    elif family == 'reddit_forum_directory':
        field = q['rank_field']
        if field not in ('submission_count', 'subscriber_count'): raise ValueError('Unsupported rank')
        table = 'submissions' if field == 'submission_count' else 'forum_subscriptions'
        scope = q.get('candidate_forum_ids')
        where = ' WHERE f.id IN ('+','.join(str(integer(x)) for x in scope)+')' if scope else ''
        rows = select_rows(site, f'SELECT f.id,f.name,(SELECT count(*) FROM {table} s WHERE s.forum_id=f.id) AS count FROM forums f'+where+' ORDER BY f.id')
        if not rows: raise ValueError('No forums to rank')
        top = max(r['count'] for r in rows)
        values = {'forum_name': sorted(r['name'] for r in rows if r['count'] == top)}
    elif family == 'reddit_post_page':
        ids = q['candidate_post_ids']
        if not ids or len(ids) != len(set(ids)): raise ValueError('Missing page scope')
        rows = select_rows(site, 'SELECT id,title,comment_count,visibility FROM submissions WHERE id IN ('+','.join(str(integer(x)) for x in ids)+') ORDER BY id')
        if len(rows) != len(ids) or any(r['visibility'] != 'visible' for r in rows): raise ValueError('Post page scope changed')
        top = max(r['comment_count'] for r in rows)
        values = {'title': sorted(r['title'] for r in rows if r['comment_count'] == top)}
    else: raise ValueError('Unsupported Reddit query family')
    if set(values) != set(q['fields']): raise ValueError('Unsupported query fields')
    return {'object_id':family+':'+str(ident), 'values':values}


def forum_cards(page):
    result = []
    for item in page.locator('article').all():
        links = item.locator('h2 a[href^="/f/"]')
        if links.count() != 1: continue
        path = urlsplit(links.get_attribute('href')).path
        name = unquote(path.removeprefix('/f/'))
        counts = item.locator('p.fg-muted').all_inner_texts()
        sub = item.locator('.subscribe-form button').inner_text().strip()
        m = re.search(r'(\d[\d,]*)\s*$', sub)
        if len(counts) != 1 or not m: raise ValueError('Forum card counts unavailable')
        result.append({'name':name,'submission_count':count_label(counts[0], 'submission'),
                       'subscriber_count':int(m[1].replace(',', ''))})
    if not result: raise ValueError('No native forum cards')
    return result


def post_article(page, q):
    # Native vote metadata supplies object identity; no title-only matching.
    article = page.locator('article.submission').filter(has=page.locator(f'form[data-vote-route-value="submission_vote"][data-vote-id-value="{integer(q["object_id"])}"]'))
    if article.count() != 1: raise ValueError('UI post identity missing or ambiguous')
    if article.locator('.submission__title').inner_text().strip() != q['object_name']: raise ValueError('Wrong rendered post title')
    return article


def ui_values(page, q):
    family = q['family']; values = {}
    if family=='reddit_forum_names':
        from .reddit_forum_list import read_forum_list
        prefix=forum_prefix(q);state=read_forum_list(page)
        if urlsplit(page.url).path.rstrip('/')!='/forums/all' or state['active_tabs']!=['Alphabetical'] or state['sort_labels']:
            raise ValueError('Full native alphabetical directory required')
        rows=[];seen=set()
        for entry in state['entries']:
            path=unquote(entry['path'])
            if not re.fullmatch(r'/f/[^/]+',path):raise ValueError('Invalid native forum link')
            name=path.removeprefix('/f/')
            if name in seen or entry['label']!=name or entry['group']!=name[0].upper():
                raise ValueError('Forum name, grouping or identity mismatch')
            seen.add(name)
            if name.casefold().startswith(prefix):rows.append({'name':name})
        return {'items':rows}
    if family == 'reddit_post':
        article = post_article(page, q)
        for field in q['fields']:
            if field == 'author': value = article.locator('.submission__submitter').inner_text().strip()
            elif field == 'title': value = article.locator('.submission__title').inner_text().strip()
            elif field == 'submission_date': value = displayed_date(article.locator('time.submission__timestamp').get_attribute('title'))
            elif field == 'comment_count':
                labels = [x.strip() for x in article.locator('.submission__nav a').all_inner_texts() if re.fullmatch(r'(?:No|[\d,]+) comments?', x.strip())]
                if len(labels) != 1: raise ValueError('Comment label missing or ambiguous')
                value = count_label(labels[0], 'comment')
            elif field == 'net_score': value = int(article.locator('.vote__net-score').inner_text().strip().replace(',', '').replace('−', '-'))
            else: raise ValueError('Unsupported UI post field')
            values[field] = value
    elif family == 'reddit_account':
        sidebar = page.locator('.sidebar__section').filter(has=page.locator('h1.sidebar__title'))
        matches = [s for s in sidebar.all() if s.locator('h1.sidebar__title').inner_text().strip() == q['username']]
        if len(matches) != 1: raise ValueError('Account sidebar identity mismatch')
        section = matches[0]
        for field in q['fields']:
            if field == 'registration_date': value = displayed_date(section.locator('header time').get_attribute('title'))
            elif field == 'whitelisted':
                labels = section.locator('header small').all_inner_texts()
                labels = [x.strip().lower() for x in labels if x.strip().lower() in ('whitelisted', 'not whitelisted')]
                if len(labels) != 1: raise ValueError('Whitelisting label unavailable')
                value = 'yes' if labels[0] == 'whitelisted' else 'no'
            else: raise ValueError('Unsupported UI account field')
            values[field] = value
    elif family == 'reddit_forum_directory':
        cards = forum_cards(page); field = q['rank_field']; top = max(r[field] for r in cards)
        # Native descending directory order makes the first page contain a global maximum.
        if urlsplit(page.url).path != q['reference_path']: raise ValueError('Wrong directory scope')
        if q.get('candidate_forum_names') and sorted(r['name'] for r in cards) != sorted(q['candidate_forum_names']): raise ValueError('Initial forum page changed')
        values = {'forum_name': sorted(r['name'] for r in cards if r[field] == top)[0]}
    elif family == 'reddit_post_page':
        rows = []
        for article in page.locator('article.submission').all():
            ident = article.locator('form[data-vote-route-value="submission_vote"]').get_attribute('data-vote-id-value')
            labels = [x.strip() for x in article.locator('.submission__nav a').all_inner_texts() if re.fullmatch(r'(?:No|[\d,]+) comments?', x.strip())]
            if len(labels) != 1: raise ValueError('Post count missing')
            rows.append({'id':int(ident),'title':article.locator('.submission__title').inner_text().strip(),'count':count_label(labels[0], 'comment')})
        if sorted(r['id'] for r in rows) != sorted(q['candidate_post_ids']): raise ValueError('Initial post page changed')
        top = max(r['count'] for r in rows)
        values = {'title': sorted(r['title'] for r in rows if r['count'] == top)[0]}
    else: raise ValueError('Unsupported native Reddit query')
    return values
