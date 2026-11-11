"""Passive reader for the installed GitLab group tree and CPU control helpers.

Native group_item renders li#group-ID[data-testid=group-overview-item-ID];
has-children and is-open are its actual Vue state classes. No DOM is modified.
Expansion helpers are for control verification, not an actor execution policy.
"""
import re

ROW = 'li.group-row[id^="group-"][data-testid^="group-overview-item-"]'
READ = r'''() => {
 const selector='li.group-row[id^="group-"][data-testid^="group-overview-item-"]';
 const shown=e=>{const r=e.getBoundingClientRect();return !!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth;};
 const main=document.querySelector('main.content,#content-body')||document.querySelector('main');
 const rows=main?[...main.querySelectorAll(selector)].filter(shown):[];
 return {url:location.href,title:document.title,body_page:document.body.dataset.page,
   account_id:window.gon?.current_user_id??null,capture_truncated:false,
   rows:rows.filter(e=>/^group-\d+$/.test(e.id)&&e.dataset.testid==='group-overview-item-'+e.id.slice(6)).map(e=>({
     id:e.id.slice(6),
     links:[...e.querySelectorAll('a[href]')].filter(a=>shown(a)&&a.closest(selector)===e).map(a=>({path:new URL(a.href).pathname,text:a.innerText.trim()})),
     expanded_controls:[],
     own_expanded:e.classList.contains('has-children')?String(e.classList.contains('is-open')):null}))};
}'''


def row_selector(group_id):
    value = str(group_id)
    if not re.fullmatch(r'[1-9][0-9]*', value):
        raise ValueError('Positive native group ID required')
    return f'li.group-row#group-{value}[data-testid="group-overview-item-{value}"]'


def capture(page):
    return page.evaluate(READ)


def wait_for_group(page, group_id, *, timeout=15000):
    row = page.locator(row_selector(group_id))
    row.wait_for(state='visible', timeout=timeout)
    if row.count() != 1:
        raise ValueError('Native group row is ambiguous')
    return row


def expand_for_control(page, group_id, child_id, *, timeout=15000):
    """Click the native caret, retaining strict row ownership and child identity."""
    row = wait_for_group(page, group_id, timeout=timeout)
    if not row.evaluate('(e)=>e.classList.contains("has-children")'):
        raise ValueError('Native group has no expansion capability')
    before = row.evaluate('(e)=>e.classList.contains("is-open")')
    if before:
        raise ValueError('Declared initial control must be collapsed')
    caret = row.locator(':scope > .group-row-contents > .folder-toggle-wrap > .folder-caret')
    if caret.count() != 1:
        raise ValueError('Native owned expansion caret absent or ambiguous')
    caret.click(timeout=timeout)
    wait_for_group(page, child_id, timeout=timeout)
    after = row.evaluate('(e)=>e.classList.contains("is-open")')
    if not after:
        raise ValueError('Visible child without native expanded parent state')
    return {'group_id': group_id, 'before': before, 'after': after, 'child_id': child_id}
