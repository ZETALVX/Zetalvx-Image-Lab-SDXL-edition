"""Caption policy versioning. New jobs preserve saved text; old resumes preserve semantics.

Changed in 0.1.0.18. The optimizer, image preparation and tokenizer are not changed.
"""
from __future__ import annotations
import re

SAVED_TEXT = 'saved_text_v1'
LEGACY = 'legacy_prefix'
POLICIES = {SAVED_TEXT, LEGACY}

def job_policy(job):
    # A pre-policy job always resumes with the exact previous treatment.
    value = job.get('caption_policy', LEGACY)
    if value not in POLICIES:
        raise ValueError('Unknown training caption policy: '+str(value))
    return value

def training_caption(item, dataset, job=None):
    policy = job_policy(job or {})
    if policy == SAVED_TEXT:
        value = item.get('caption', '')
        if not isinstance(value, str):
            raise ValueError('A saved caption must be text.')
        return value  # Including whitespace. Empty captions stay empty, no invented trigger.
    cap = (item.get('caption') or dataset.get('common_caption') or dataset.get('trigger') or '').strip()
    trigger = str(dataset.get('trigger') or '').strip()
    if not trigger:
        return cap
    rest = re.sub(re.escape(trigger), '', cap, flags=re.I)
    rest = re.sub(r'\s+,', ',', rest)
    rest = re.sub(r',\s*,+', ', ', rest)
    rest = re.sub(r'\s+', ' ', rest).strip(' ,')
    return f'{trigger}, {rest}' if rest else trigger


def _token_count(tokenizer,text):
    return len(tokenizer(str(text or ''),truncation=False,add_special_tokens=True).input_ids)

def _fits(tokenizer,text,limit):
    try:return _token_count(tokenizer,text)<=int(limit)
    except Exception:return True

def _shrink_end(tokenizer,text,limit):
    text=str(text or '')
    if _fits(tokenizer,text,limit):return text
    lo,hi,best=0,len(text),''
    while lo<=hi:
        mid=(lo+hi)//2;candidate=text[:mid].rstrip(' ,.;:-')
        if _fits(tokenizer,candidate,limit):best=candidate;lo=mid+1
        else:hi=mid-1
    return best

def _shrink_start(tokenizer,text,limit):
    text=str(text or '')
    if _fits(tokenizer,text,limit):return text
    lo,hi,best=0,len(text),''
    while lo<=hi:
        mid=(lo+hi)//2;candidate=text[len(text)-mid:].lstrip(' ,.;:-') if mid else ''
        if _fits(tokenizer,candidate,limit):best=candidate;lo=mid+1
        else:hi=mid-1
    return best

def clip_training_caption(caption,dataset,tokenizer,limit=None):
    """Return only the effective CLIP caption. Never mutates saved dataset text.

    The selected trigger placement is preserved when the literal trigger is present.
    Prefix keeps the beginning, suffix keeps the end, and context keeps the trigger
    with balanced surrounding text.
    """
    cap=str(caption or '');trigger=str((dataset or {}).get('trigger') or '').strip()
    position=str((dataset or {}).get('trigger_position') or 'context')
    max_len=int(limit or getattr(tokenizer,'model_max_length',77) or 77)
    if _fits(tokenizer,cap,max_len):return cap
    if not trigger or trigger.lower() not in cap.lower():return _shrink_end(tokenizer,cap,max_len)
    m=re.search(re.escape(trigger),cap,flags=re.I)
    if not m:return _shrink_end(tokenizer,cap,max_len)
    before,actual,after=cap[:m.start()].strip(' ,'),cap[m.start():m.end()],cap[m.end():].strip(' ,')
    if position=='prefix':
        base=(actual+', ') if after else actual
        room=lambda x: base+x
        return room(_shrink_end(tokenizer,after,max_len)) if _fits(tokenizer,room(_shrink_end(tokenizer,after,max_len)),max_len) else _shrink_end(tokenizer,base,max_len)
    if position=='suffix':
        suffix=(', '+actual) if before else actual
        # Keep the trigger at the end; remove text from the beginning until the composition fits.
        if _fits(tokenizer,suffix,max_len):
            lo,hi,best=0,len(before),''
            while lo<=hi:
                mid=(lo+hi)//2;left=before[:mid].rstrip(' ,');candidate=(left+suffix) if left else actual
                if _fits(tokenizer,candidate,max_len):best=candidate;lo=mid+1
                else:hi=mid-1
            return best or actual
        return _shrink_start(tokenizer,actual,max_len)
    # In-context: preserve the literal trigger and approximately equal context on both sides.
    if not _fits(tokenizer,actual,max_len):return _shrink_end(tokenizer,actual,max_len)
    left,right=before,after
    while left or right:
        candidate=', '.join(x for x in (left,actual,right) if x)
        if _fits(tokenizer,candidate,max_len):return candidate
        if len(left)>=len(right) and left:left=left[:-max(1,len(left)//12)].rstrip(' ,.;:-')
        elif right:right=right[:max(0,len(right)-max(1,len(right)//12))].rstrip(' ,.;:-')
        else:break
    return actual
