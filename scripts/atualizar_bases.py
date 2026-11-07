#!/usr/bin/env python3
"""Atualizador de FONTES PÚBLICAS para o BDC Nutri.

Executado pela GitHub Actions. Baixa apenas dados nutricionais oficiais,
converte o Foundation Foods em arquivo JSON de dados e publica catálogo SHA256.
Não acessa cadastro, pacientes, avaliações ou dietas.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import zipfile
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent.parent
PUBLIC = HERE / 'site'
MANIFEST = PUBLIC / 'bdc-bases-manifest.json'
USDA_PAGE = 'https://fdc.nal.usda.gov/download-datasets/'
IBGE_FILE = ('https://ftp.ibge.gov.br/Orcamentos_Familiares/'
             'Pesquisa_de_Orcamentos_Familiares_2008_2009/'
             'Tabelas_de_Composicao_Nutricional_dos_Alimentos_Consumidos_no_Brasil/'
             'tabelacompleta.zip')
S = requests.Session()
S.headers['User-Agent'] = 'BDC-Nutri-PublicDataMonitor/1.0 (public food composition)'


def download(url: str, limit: int = 16_000_000) -> bytes:
    if not url.startswith('https://'):
        raise ValueError('Somente URLs HTTPS permitidas.')
    r = S.get(url, stream=True, timeout=(15, 70)); r.raise_for_status()
    if not r.url.startswith('https://'):
        raise ValueError('Redirecionamento para URL não segura.')
    out = bytearray()
    for chunk in r.iter_content(512 * 1024):
        out.extend(chunk)
        if len(out) > limit:
            raise ValueError('Arquivo excede limite de segurança.')
    return bytes(out)


def find_foundation_download(html: str):
    soup = BeautifulSoup(html, 'html.parser')
    for tr in soup.select('tr'):
        cells = tr.find_all(['td','th'])
        if not cells or 'foundation foods' not in cells[0].get_text(' ', strip=True).lower():
            continue
        full = tr.get_text(' ', strip=True)
        link = next((a.get('href') for a in tr.find_all('a') if 'json' in a.get_text(' ',strip=True).lower()), None)
        if not link:
            continue
        url = urljoin(USDA_PAGE,link)
        if urlparse(url).netloc != 'fdc.nal.usda.gov' or not url.lower().endswith('.zip'):
            raise ValueError('Endereço da USDA inesperado; revisão necessária.')
        date_text = cells[1].get_text(' ',strip=True) if len(cells)>1 else ''
        m = re.search(r'(\d{1,2})\s*/\s*(\d{4})', date_text)
        if not m:
            raise ValueError('Data da edição Foundation não encontrada.')
        version = f'{m.group(2)}-{int(m.group(1)):02d}'
        return version,url
    raise ValueError('Página da USDA mudou de formato; revisão necessária.')


def read_official_foundation(zip_bytes: bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        possible = [n for n in z.namelist() if n.lower().endswith('.json')
                    and '..' not in Path(n).parts and not n.startswith('/')]
        if not possible:
            raise ValueError('Arquivo oficial sem JSON reconhecível.')
        for n in possible:
            item = z.getinfo(n)
            if item.file_size > 120_000_000:
                raise ValueError('JSON de tamanho excessivo.')
            with z.open(n) as f:
                parsed = json.load(f)
            candidates = (parsed.get('FoundationFoods') or parsed.get('foundationFoods')
                          or parsed.get('foods') or parsed.get('Food') or []) if isinstance(parsed,dict) else parsed
            if isinstance(candidates,list) and len(candidates)>=200:
                return candidates
    raise ValueError('Não foi encontrada uma lista completa de Foundation Foods.')


def nutrient_id(n):
    nutrient=n.get('nutrient') or {}
    try:return int(nutrient.get('id') or n.get('nutrientId') or -1)
    except (ValueError,TypeError):return -1


def convert_foundation(raw: list, version: str):
    foods=[]; ids=set()
    for f in raw:
        if not isinstance(f,dict): continue
        identifier=f.get('fdcId') or f.get('fdc_id')
        try: fid=int(identifier)
        except (TypeError,ValueError):continue
        if fid<10000 or fid in ids:raise ValueError('IDs USDA inválidos ou repetidos')
        ids.add(fid)
        name=str(f.get('description','')).strip()
        if not name or len(name)>220:continue
        nuts={}; individual={}
        for n in f.get('foodNutrients',[]):
            if not isinstance(n,dict):continue
            nut=n.get('nutrient') or {}
            v=n.get('amount',n.get('value'))
            try:v=float(v)
            except (ValueError,TypeError):continue
            if not (0<=v<=1_000_000):continue
            key=nutrient_id(n)
            nuts[key]=v
            label=str(nut.get('name') or '').strip()
            unit=str(nut.get('unitName') or '').strip()
            if label and len(label)<100 and unit and len(unit)<20:
                individual[f'{label} ({unit})']=v
        # De acordo com os identificadores FDC: 2048/2047 kCal calculados; 1008 energia.
        energy=next((nuts[i] for i in (2048,2047,1008) if i in nuts),None)
        protein=nuts.get(1003); fat=nuts.get(1004); carbs=nuts.get(1005)
        cat=f.get('foodCategory') or {}
        cat=cat.get('description','') if isinstance(cat,dict) else str(cat)
        portions=[]
        for p in f.get('foodPortions',[]):
            if not isinstance(p,dict):continue
            grams=p.get('gramWeight')
            try:grams=float(grams)
            except (TypeError,ValueError):continue
            if not 0<grams<10000:continue
            measure=p.get('measureUnit') or {}
            measure=measure.get('name','') if isinstance(measure,dict) else str(measure)
            label=' '.join(str(x).strip() for x in (p.get('amount') or '',measure,p.get('modifier') or p.get('portionDescription') or '') if x not in (None,''))
            portions.append([label[:120] or 'Porção',round(grams,3)])
        foods.append({'id':f'usda_foundation_{fid}', 'code':str(fid),'name':name,
                      'state':'Não especificado','category':str(cat)[:140],
                      'kcal':energy,'p':protein,'c':carbs,'g':fat,
                      'nutrients':individual,'portions':portions[:150]})
    if len(foods)<200 or len(foods)>5000:raise ValueError(f'Contagem USDA suspeita: {len(foods)}')
    return {'schema':'bdc-food-data-v1','source':'USDA_FOUNDATION','version':version,'foods':foods}


def sync_foundation(mf):
    version,url=find_foundation_download(download(USDA_PAGE,2_000_000).decode('utf-8'))
    existing=mf['sources']['USDA_FOUNDATION']
    print('USDA Foundation, edição oficial:',version)
    # Consultar também o conteúdo, pois um arquivo pode ser corrigido mantendo a data de edição.
    blob=download(url,20_000_000)
    source_hash=hashlib.sha256(blob).hexdigest()
    if existing.get('upstreamSha256')==source_hash and existing.get('dataUrl'):
        print('  Sem mudança no arquivo oficial.');return False
    # Revisões oficiais com a mesma data também merecem um identificador exclusivo.
    outgoing_version=version
    if existing.get('version','').startswith(version) and existing.get('upstreamSha256') not in (None,source_hash):
        outgoing_version=version+'-rev-'+source_hash[:10]
    pack=convert_foundation(read_official_foundation(blob),outgoing_version)
    target=PUBLIC/'food-packs'/f'foundation-{outgoing_version}.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    serialized=json.dumps(pack,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    target.write_bytes(serialized)
    mf['sources']['USDA_FOUNDATION']={
        'version':outgoing_version,'status':'disponivel',
        'dataUrl':'./food-packs/'+target.name,
        'sha256':hashlib.sha256(serialized).hexdigest(),
        'upstreamSha256':source_hash,'count':len(pack['foods']),
        'sourceUrl':url,'publishedBy':'USDA FoodData Central',
    }
    print('  Publicados',len(pack['foods']),'alimentos.')
    return True


def sync_ibge(mf):
    data=download(IBGE_FILE,4_000_000)
    digest=hashlib.sha256(data).hexdigest()
    item=mf['sources']['IBGE']
    if not item.get('upstreamSha256'):
        item['upstreamSha256']=digest
        print('IBGE: assinatura oficial inicial registrada, sem alterar a base instalada.')
        return True
    if digest==item['upstreamSha256']:
        print('IBGE: arquivo oficial sem mudanças.');return False
    # O IBGE disponibiliza dados em tabelas, não no esquema BDC. Nunca instalar bruto.
    # Uma nova edição de POF pode não ter metodologia / ids comparáveis à de 2008–2009.
    item['status']='revisao-pendente-validacao'
    item['previousSha256']=item['upstreamSha256']
    item['upstreamSha256']=digest
    item['detectedHash']=digest
    item['sourceUrl']=IBGE_FILE
    item['notes']='Arquivo oficial mudou; aguardando conversão e validação para evitar misturar metodologias.'
    print('IBGE: revisão detectada, não há pacote compatível automaticamente.');return True


def main():
    if not MANIFEST.exists():raise RuntimeError('Catálogo não encontrado')
    mf=json.loads(MANIFEST.read_text('utf-8'))
    if mf.get('schema')!='bdc-food-updates-v1':raise ValueError('Catálogo inválido')
    changed=False;errors=[]
    for label,fn in [('USDA Foundation',sync_foundation),('IBGE',sync_ibge)]:
        try:changed|=fn(mf)
        except Exception as e:
            errors.append(f'{label}: {e}')
            print('AVISO: ',errors[-1],file=sys.stderr)
    if changed:
        mf['generatedAt']=datetime.now(timezone.utc).isoformat(timespec='seconds')
        MANIFEST.write_text(json.dumps(mf,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if errors:
        print('Falhas de consulta; nenhuma atualização inválida foi publicada.',file=sys.stderr)
        # Uma fonte indisponível não deve impedir a publicação da outra.
        return 1 if len(errors)==2 else 0
    return 0

if __name__=='__main__':sys.exit(main())
