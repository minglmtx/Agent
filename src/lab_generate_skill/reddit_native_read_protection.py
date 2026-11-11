"""Private complete read-only native coverage and actual public capabilities.

The existing twelve full task-table guards are retained. All submission rows
and columns are additionally hashed in indexed bounded chunks. This is an
explicit thirteen-table protocol, not a claim that every PostgreSQL relation
or external service is unchanged.
"""
import json
import re
from pathlib import Path

from lab_generate_skill.site_database import select_rows

VERSION = 'reddit45-readonly-complete13-v1'
MARKDOWN_TEMPLATE_SHA = '48cd271d3c3974b5d4b6150295705322c68af486591d00b400de6d8bf6f60779'
MARKDOWN_TRANSLATIONS_SHA = '241df445137362b1b4519e401828b9d1437fbba4654a4f1e57740b0afeaf0d18'

DOC_REFERENCE = r'''require '/var/www/html/vendor/autoload.php';
$template='/var/www/html/templates/_forms/markdown.html.twig';
$translations='/var/www/html/translations/messages.en.yml';
$v=Symfony\Component\Yaml\Yaml::parseFile($translations);
$keys=['markdown.link','markdown.forum','markdown.user','markdown.wiki_page'];$values=[];
foreach($keys as $k){if(!isset($v[$k])||!is_string($v[$k])||!strlen($v[$k]))throw new RuntimeException('Native translation missing');$values[$k]=$v[$k];}
echo json_encode(['template_sha256'=>hash_file('sha256',$template),
 'translation_sha256'=>hash_file('sha256',$translations),'translations'=>$values]);'''


def submission_snapshot(site, out):
    """Read every original row/column through one fresh read-only connection.

    This preserves the full native PK-order checksum and starts no cache.
    The other twelve table guards remain independently captured on every call.
    """
    from .reddit_submission_snapshot_stream import submission_snapshot as scan
    return scan(site, out)


def complete_snapshot(site, out):
    from .reddit_exact_forum_runtime import protected_snapshot as safe_digest
    from lab_generate_skill.reddit_protected_chunks import validate_snapshot
    names = ','.join("'" + name + "'" for name in (
        'forums','comments','submission_votes','comment_votes','wiki_pages',
        'wiki_revisions','forum_tags','forums_tags','hidden_forums',
        'forum_subscriptions','user_blocks','users'))
    present = select_rows(site, "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN (" + names + ') ORDER BY table_name')
    if (not isinstance(present, list) or len(present) != 12
            or len({row.get('table_name') for row in present}) != 12):
        raise ValueError('Every declared native protected table must exist')
    task_tables = safe_digest(site); validate_snapshot(task_tables)
    return {'version': VERSION, 'twelve_task_tables': task_tables,
            'submissions': submission_snapshot(site, out),
            'users_only_ignored_column': 'last_seen'}


def formatting_reference(site, form_kind='wiki'):
    """Independently read shipped template/translation bytes, never live answer."""
    from .reddit_native_formatting_navigation import validate
    response = site.command(['php', '-r', DOC_REFERENCE], capture_output=True, text=True, timeout=30)
    value = json.loads(response.stdout)
    if (set(value) != {'template_sha256', 'translation_sha256', 'translations'}
            or value['template_sha256'] != MARKDOWN_TEMPLATE_SHA
            or value['translation_sha256'] != MARKDOWN_TRANSLATIONS_SHA):
        raise ValueError('Installed native documentation changed; explicit rereview required')
    keys = ('markdown.link', 'markdown.forum', 'markdown.user', 'markdown.wiki_page')
    translations = value['translations']
    if set(translations) != set(keys) or any(not isinstance(translations[k], str) or not translations[k] for k in keys):
        raise ValueError('Complete native documentation translations required')
    link, forum, user, wiki = [translations[k] for k in keys]
    # These literal structural prefixes and example URL are from the exact
    # pinned native Twig row, not additional generated documentation or actions.
    suffix = f'/f/{forum} /u/{user} /w/{wiki}'
    spec = {'form_kind': form_kind, 'required_rows': [
        {'feature': link + ' ' + suffix, 'syntax': f'[{link}](http://example.com) ' + suffix}]}
    validate(spec)
    return {'spec': spec, 'native_sources': value}


def directory_reference(site):
    return {'forums': select_rows(site, 'SELECT id,name,title,description FROM forums ORDER BY id'),
            'wiki_pages': select_rows(site, 'SELECT id,path,normalized_path FROM wiki_pages ORDER BY id'),
            'forum_tags': select_rows(site, 'SELECT id,name,normalized_name,description FROM forum_tags ORDER BY id')}
