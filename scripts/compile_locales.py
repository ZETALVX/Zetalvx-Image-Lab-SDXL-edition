#!/usr/bin/env python3
"""Build offline locale-catalog.js using editable UTF-8 JSON files, standard library only."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
config=json.loads((ROOT/'static/locales/sources.json').read_text('utf8'))
translations={}
for lang in config['languages']:
    translations[lang['code']]=json.loads((ROOT/'static/locales'/f"{lang['code']}.json").read_text('utf8'))
entries=[]
for sources in config['sources']:
    key=sources[0];text={}
    for lang in config['languages']:
        code=lang['code'];value=translations[code].get(key)
        if not isinstance(value,str) or not value:raise SystemExit(f'Missing message: {code}: {key}')
        if set(re.findall(r'\{(\w+)\}',key))!=set(re.findall(r'\{(\w+)\}',value)):raise SystemExit(f'Placeholder mismatch: {code}: {key}')
        text[code]=value
    entries.append({'sources':sources,'text':text})
(ROOT/'static/locale-catalog.js').write_text('window.ZETALVX_LOCALES='+json.dumps({'languages':config['languages'],'entries':entries},ensure_ascii=False,separators=(',',':'))+';\n','utf8')
print(f'Compiled {len(entries)} messages in {len(config["languages"])} languages')
