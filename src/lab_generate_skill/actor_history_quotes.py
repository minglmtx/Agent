"""Optional lossy historical-page views with verbatim, traceable public quotes.

The current observation and full execution records are never edited here.
Selection uses observed targets, page headers and changed public lines; it
does not infer intent, persistence, correctness or the task's expected answer.
"""
from collections import Counter
import copy
import re

VERSION = 'related-public-history-quotes-v1'


def page_text(page):
    text = page['observation']
    if (page.get('observation_mode') == 'full'
            and page.get('observation_policy') == 'full-lossless-rows-if-fits-v2'):
        from .lossless_ax_rows import expand
        return expand(text)
    return text


def signature(line):
    # Ignore transient IDs for selection only. Output retains original lines.
    return re.sub(r'^\s*\[[^\]\s]+\]\s*', '', line).strip()


def related_quotes(page, *, targets=(), previous_pages=(), maximum_lines=32):
    if type(maximum_lines) is not int or maximum_lines < 1:
        raise ValueError('Positive whole-line history limit required')
    lines = page_text(page).splitlines()
    priorities = []

    def add(index, reason):
        if 0 <= index < len(lines) and not any(row[0] == index for row in priorities):
            priorities.append((index, reason))

    # The target itself is also preserved in the associated action record.
    for target in targets:
        for i, line in enumerate(lines):
            if line.strip() != target.get('observed_node'):
                continue
            add(i, 'actual_action_target')
            indent = len(line) - len(line.lstrip())
            parent_indent = indent
            parents = 0
            for j in range(i - 1, -1, -1):
                width = len(lines[j]) - len(lines[j].lstrip())
                if lines[j].strip() and width < parent_indent:
                    add(j, 'target_ancestor'); parent_indent = width; parents += 1
                    if parents == 3:
                        break
            for j in range(i - 1, i + 3):
                add(j, 'target_neighbor')
    for i in range(min(4, len(lines))):
        add(i, 'page_header')
    for i, line in enumerate(lines):
        if 'focused' in line and ('[' in line or 'RootWebArea' in line):
            add(i, 'reported_focus')
    changed = []
    for previous in previous_pages:
        counts = Counter(signature(line) for line in page_text(previous).splitlines())
        for i, line in enumerate(lines):
            key = signature(line)
            if counts[key]:
                counts[key] -= 1
            elif i not in changed:
                changed.append(i)
    for i in changed[:12] + changed[-4:]:
        add(i, 'changed_public_line')
    # A bounded textual sample remains useful for pages without a target or
    # predecessor. It is explicitly an excerpt, never a complete page claim.
    for i in range(len(lines)):
        add(i, 'remaining_in_page_order')
        if len(priorities) >= maximum_lines:
            break
    selected = sorted(priorities[:maximum_lines])
    chunks, last = [], -1
    for index, reason in selected:
        if index > last + 1:
            chunks.append('[Historical excerpt: %d original lines omitted.]' % (index - last - 1))
        chunks.append(lines[index]); last = index
    if last + 1 < len(lines):
        chunks.append('[Historical excerpt: %d original lines omitted.]' % (len(lines) - last - 1))
    view = copy.deepcopy(page)
    view['observation'] = '\n'.join(chunks)
    view['observation_scope'] = 'Historical public excerpt; omitted lines are declared. This is not the current page.'
    view['observation_mode'] = 'historical_excerpt'
    view['observation_policy'] = VERSION
    view['historical_view'] = dict(version=VERSION, lossy=len(selected) < len(lines),
        original_lines=len(lines), retained_lines=len(selected), omitted_lines=len(lines)-len(selected),
        content_kind='verbatim_public_lines_not_a_summary', current_state_asserted=False)
    if page_text(page) != page['observation']:
        view['historical_view']['expanded_from_lossless_rows'] = True
        # The quotes are plain AX; the original rows stay in the raw audit.
    audit = dict(version=VERSION, selected_lines=[dict(index=i, reason=r) for i,r in selected],
                 original_lines=len(lines), maximum_lines=maximum_lines,
                 original_observation_policy=page.get('observation_policy'),
                 original_observation_mode=page.get('observation_mode'))
    return view, audit
