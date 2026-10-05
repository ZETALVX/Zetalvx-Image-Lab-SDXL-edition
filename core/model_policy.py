"""Distribution policy, not a legal certification. Weights keep their own terms."""
from urllib.parse import urlsplit, unquote

POLICY_VERSION = '2026-09-20.1'
SDXL_REPO = 'stabilityai/stable-diffusion-xl-base-1.0'
SDXL_FILE = 'sd_xl_base_1.0.safetensors'
SDXL_SHA256 = '31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b'
CATALOG = [
    dict(id='sdxl_base', name='SDXL Base 1.0', mode='install', kind='checkpoint',
         source=f'https://huggingface.co/{SDXL_REPO}',
         url=f'https://huggingface.co/{SDXL_REPO}/resolve/main/{SDXL_FILE}',
         sha256=SDXL_SHA256, license='CreativeML Open RAIL++-M',
         license_url=f'https://huggingface.co/{SDXL_REPO}/blob/main/LICENSE.md',
         note='Uso e redistribuzione soggetti alla licenza del modello e alle restrizioni d’uso.'),
    dict(id='instantid_code', name='Codice InstantID', mode='code', license='Apache-2.0',
         source='https://github.com/instantX-research/InstantID',
         note='Solo codice; nessun peso facciale incluso.'),
    dict(id='instantid', name='Pesi InstantID', mode='external', license='Research-only (upstream disclaimer)',
         source='https://huggingface.co/InstantX/InstantID',
         license_url='https://github.com/instantX-research/InstantID#disclaimer'),
    dict(id='antelopev2', name='Face encoder · antelopev2', mode='external', license='Non-commercial research',
         source='https://github.com/instantX-research/InstantID#download',
         license_url='https://github.com/deepinsight/insightface#license'),
    dict(id='buffalo_l', name='Face analysis · buffalo_l', mode='external', license='Non-commercial research',
         source='https://github.com/deepinsight/insightface',
         license_url='https://github.com/deepinsight/insightface#license'),
    dict(id='inswapper', name='Face Swap · inswapper', mode='external', license='Termini separati / autorizzazione commerciale',
         source='https://github.com/deepinsight/insightface#license',
         license_url='https://github.com/deepinsight/insightface#license'),
]

def catalog():
    return [dict(x, policy_version=POLICY_VERSION) for x in CATALOG]

def external_reason(url):
    """Known restricted integrations cannot be re-enabled using the URL importer.
    This is not an exhaustive license classifier for arbitrary third-party files.
    """
    p=urlsplit(str(url));path=unquote(p.path).lower();host=(p.hostname or '').lower()
    if any(x in path for x in ('inswapper','antelopev2','buffalo_l')):
        return 'Componente Identity esterno: apri la fonte ufficiale e collega i file per cui hai i diritti necessari.'
    if host in ('huggingface.co','www.huggingface.co') and path.startswith(('/instantx/instantid/','/instantx/instantid-')):
        return 'I checkpoint InstantID restano esterni in questa distribuzione. Usa la configurazione Identity.'
    return ''
