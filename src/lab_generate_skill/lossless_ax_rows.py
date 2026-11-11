"""Reversible shorthand for consecutive leaf gridcells; no task or DOM lookup."""
import ast,re
START='@AX-ROWS-v1 '
END='@END-AX-ROWS'
GUIDANCE='AX-ROWS is lossless AX shorthand. Each [n] line represents an empty-name row [n]; its comma-separated string names belong to gridcells [n+1], [n+2], etc., in order. Depth is the original tab indentation. All cell values and element IDs remain present; use the calculated cell ID for actions. Other AX lines are unchanged.'

def _row(lines,i):
    match=re.fullmatch(r"(\t*)\[([1-9][0-9]*)\] row ''",lines[i])
    if not match:return None
    depth=len(match[1]);base=int(match[2]);j=i+1;values=[]
    while j<len(lines)and len(lines[j])-len(lines[j].lstrip('\t'))>depth:
        cell=re.fullmatch(r'\t{'+str(depth+1)+r'}\[([1-9][0-9]*)\] gridcell (.+)',lines[j])
        if not cell or int(cell[1])!=base+len(values)+1:return None
        try:
            value=ast.parse(cell[2],mode='eval').body
            if not isinstance(value,ast.Constant)or type(value.value)is not str:return None
        except (SyntaxError,ValueError):return None
        values.append(cell[2]);j+=1
    if not values or len(values)>64:return None
    return depth,base,values,j

def compact(text):
    if not isinstance(text,str):raise TypeError('AX text required')
    lines=text.split('\n')
    if any(line.startswith((START,END))for line in lines):return text
    out=[];i=0
    while i<len(lines):
        first=_row(lines,i)
        if first is None:out.append(lines[i]);i+=1;continue
        rows=[first];j=first[3]
        while j<len(lines):
            row=_row(lines,j)
            if row is None or row[0]!=first[0]:break
            rows.append(row);j=row[3]
        if len(rows)<2:out.extend(lines[i:j]);i=j;continue
        out.append(START+'depth='+str(first[0])+' count='+str(len(rows)))
        out.extend('['+str(base)+'] '+', '.join(values)for _,base,values,_ in rows)
        out.append(END);i=j
    result='\n'.join(out)
    if expand(result)!=text:raise ValueError('Lossless AX roundtrip failed')
    return result

def expand(text):
    lines=text.split('\n');out=[];i=0
    while i<len(lines):
        if not lines[i].startswith(START):out.append(lines[i]);i+=1;continue
        header=re.fullmatch(re.escape(START)+r'depth=([0-9]+) count=([0-9]+)',lines[i])
        if not header:raise ValueError('Invalid AX row block')
        depth,count=map(int,header.groups())
        if not 0<=depth<=256 or not 2<=count<=100000:raise ValueError('Invalid AX row bounds')
        i+=1
        for _ in range(count):
            if i>=len(lines):raise ValueError('Incomplete AX row block')
            row=re.fullmatch(r'\[([1-9][0-9]*)\] (.+)',lines[i])
            if not row:raise ValueError('Invalid AX row')
            source='('+row[2]+',)'
            try:parsed=ast.parse(source,mode='eval').body
            except SyntaxError as exc:raise ValueError('Invalid AX cell strings')from exc
            if not isinstance(parsed,ast.Tuple)or not 1<=len(parsed.elts)<=64 or any(not isinstance(x,ast.Constant)or type(x.value)is not str for x in parsed.elts):raise ValueError('AX cells must be literal strings')
            base=int(row[1]);out.append('\t'*depth+'['+str(base)+"] row ''")
            out.extend('\t'*(depth+1)+'['+str(base+n)+'] gridcell '+ast.get_source_segment(source,x)for n,x in enumerate(parsed.elts,1))
            i+=1
        if i>=len(lines)or lines[i]!=END:raise ValueError('Unclosed AX row block')
        i+=1
    return '\n'.join(out)
