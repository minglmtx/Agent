"""Versioned, deterministic skill length checks; no model calls or rewriting."""
import re

SKILL_BUDGET_VERSION = 'compact-soft-v2'
SOFT_WORD_LIMITS = {'title': 8, 'principle': 100, 'when_to_apply': 50}
HARD_WORD_LIMITS = {'title': 12, 'principle': 200, 'when_to_apply': 70}
SOFT_TOTAL_WORDS, HARD_TOTAL_WORDS = 160, 220
SOFT_STEPS, HARD_STEPS, SOFT_STEP_WORDS = 4, 6, 25
_NUMBERED_STEP = re.compile(r'(?m)^[ \t]*(\d+)[.)](?:[ \t]+|(?=\n|$))')
_INLINE_STEP = re.compile(r"(?<!\S)(\d+)[.)](?:[ \t]+|(?=\n|$))")
_WORD = re.compile(r"[A-Za-z0-9]+(?:['’_-][A-Za-z0-9]+)*")

SKILL_LENGTH_INSTRUCTIONS = '''Length guidance (soft targets): aim for title <=8 English words, principle <=100,
when_to_apply <=50, and <=160 words total. Prefer at most 4 main numbered steps
and about 25 words per step; a longer step is allowed when necessary for useful
conditions or completion checks. Do not omit essential instructions to meet a target.
Hard limits: title <=12 words, principle <=200, when_to_apply <=70, <=220 words
total, and at most 6 numbered steps. Field and total limits apply simultaneously.
There is no hard per-step word limit. These ceilings are not targets to fill.
For procedures, number consecutive nonempty steps from 1 within principle; prefer
separate lines and keep all procedure text inside the steps. Encode line breaks as \\n in JSON.
Plain prose is also allowed. Hyphenated words and contractions count as one word;
JSON keys and step-number labels do not count. Return only the three skill fields,
without word counts, length warnings, markdown, or additional fields.'''


def numbered_skill_steps(text):
    # Inline "1. ... 2. ..." is a list only when the principle starts with 1.
    # Decimal values such as 29.99 lack whitespace after the dot and stay content.
    first=_NUMBERED_STEP.match(text)
    pattern=_INLINE_STEP if first and int(first.group(1))==1 else _NUMBERED_STEP
    return list(pattern.finditer(text))


def skill_word_count(text):
    steps=numbered_skill_steps(text)
    for step in reversed(steps):text=text[:step.start()]+text[step.end():]
    return len(_WORD.findall(text))


def skill_length_report(skill):
    value=skill if isinstance(skill,dict) else skill.model_dump()
    counts={k:skill_word_count(value[k]) for k in SOFT_WORD_LIMITS}
    total=sum(counts.values());text=value['principle'];steps=numbered_skill_steps(text)
    step_counts=[skill_word_count(text[s.end():steps[i+1].start() if i+1<len(steps) else len(text)]) for i,s in enumerate(steps)]
    warnings=[f'{k}_soft_limit: {counts[k]} > {v}' for k,v in SOFT_WORD_LIMITS.items() if counts[k]>v]
    if total>SOFT_TOTAL_WORDS:warnings.append(f'total_soft_limit: {total} > {SOFT_TOTAL_WORDS}')
    if len(steps)>SOFT_STEPS:warnings.append(f'steps_soft_limit: {len(steps)} > {SOFT_STEPS}')
    warnings.extend(f'step_{i+1}_soft_limit: {count} > {SOFT_STEP_WORDS}' for i,count in enumerate(step_counts) if count>SOFT_STEP_WORDS)
    return {'policy_version':SKILL_BUDGET_VERSION,'word_counts':counts,'total_words':total,'numbered_steps':len(steps),'step_word_counts':step_counts,'soft_warnings':warnings}
