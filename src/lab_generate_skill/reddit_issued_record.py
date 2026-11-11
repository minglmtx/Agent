"""Match public text inside the actual AX article issued to the actor.

Inline search highlighting splits sentences into separate StaticText nodes.
Only join nodes within the same DOM-bound article; never use a hidden record,
another article, the unbudgeted full AX, or private expected answers.
"""
import ast
import re

NODE=re.compile(r'''^(\s*)(?:\[([^\]]+)\]\s+)?([\w-]+)\s+('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")''')


def norm(value):
    return ' '.join(value.split()) if isinstance(value,str) else ''


def issued_article(ax,bid):
    if not isinstance(ax,str) or not isinstance(bid,str) or not bid:
        return None
    nodes=[]
    for line in ax.splitlines():
        match=NODE.match(line)
        if not match:continue
        try:name=ast.literal_eval(match[4])
        except (ValueError,SyntaxError):continue
        nodes.append((len(match[1].expandtabs(4)),match[2],match[3],name))
    hits=[i for i,n in enumerate(nodes)if n[1]==bid and n[2]=='article']
    if len(hits)!=1:return None
    start=hits[0];depth=nodes[start][0];body=[]
    for node in nodes[start+1:]:
        if node[0]<=depth:break
        # Replies may nest other articles. They are separate record identities.
        if node[2]=='article':break
        body.append(node)
    return {'names':[norm(n[3])for n in body if isinstance(n[3],str)],
            'fragments':[norm(n[3])for n in body if n[2]=='StaticText' and norm(n[3])],
            'static_text':norm(' '.join(n[3]for n in body if n[2]=='StaticText'and isinstance(n[3],str)))}


def fragment_match(label, fragments):
    """AX strips edge spaces from text nodes split by inline markup.

    Match consecutive complete fragments, allowing only their missing boundary
    whitespace. Characters, punctuation, internal word boundaries and order
    remain exact. This never uses unissued DOM text as substitute evidence.
    """
    for start in range(len(fragments)):
        offset=0
        for fragment in fragments[start:]:
            if offset and label[offset:offset+1]==' ':
                offset+=1
            if not label.startswith(fragment,offset):
                break
            offset+=len(fragment)
            if offset==len(label):
                return True
    return False


def record_exposure(row,ax):
    label=norm(row.get('label'))
    if not label:return None
    if 'article_bid' not in row:
        # Historical receipts lack a DOM binding. Preserve their stricter old
        # rule rather than retroactively grant split-text exposure to them.
        return ax if label in norm(ax) else None
    article=issued_article(ax,row['article_bid'])
    if article is None:return None
    if (label not in article['names'] and label not in article['static_text']
            and not fragment_match(label,article['fragments'])):
        return None
    return '\n'.join(article['names'])+'\n'+article['static_text']
