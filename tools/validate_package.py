"""Validate public research-package consistency with Python standard library."""
from pathlib import Path
from collections import Counter
import json
import re

ROOT = Path(__file__).resolve().parents[1]

def validate():
    path = ROOT / 'create-funny-meme-cards/assets/knowledge'
    pack = json.loads((path / 'knowledge.json').read_text(encoding='utf-8'))
    index = json.loads((path / 'index.json').read_text(encoding='utf-8'))
    sources = {s['id']: s for s in pack['sources']}
    ids = [r['id'] for r in pack['records']]
    review = json.loads((ROOT / '知识库/收录复审.json').read_text())['entries']
    assert set(ids) == {k for k,v in review.items() if v['decision']=='include'}, 'Unreviewed or held entry exported'
    for r in pack['records']:
        assert r['language'].startswith('zh') or review[r['id']]['mainland_usage_evidence'], 'Overseas-only English entry'
    assert len(ids) == len(set(ids)), 'Duplicate entry IDs'
    assert len(sources) == len(pack['sources']), 'Duplicate source IDs'
    assert len({s['url'] for s in sources.values()}) == len(sources), 'Duplicate source URLs'
    assert [r['id'] for r in index['entries']] == ids, 'Index order or IDs differ'
    assert index['record_count'] == len(ids), 'Index count mismatch'
    for record, brief in zip(pack['records'], index['entries']):
        for key in ['id', 'title', 'language', 'kind', 'template_family']:
            assert brief[key] == record[key], f'Index mismatch: {key}'
        assert brief['social_functions'] == record['social_use']['functions']
        assert all(record['social_use'][k] for k in ['audience','trigger','line','avoid'])
        assert record['social_use']['evidence_status'] == 'editorial_example_not_audience_tested'
        assert brief['categories'] == record['categories']
        assert brief['recent_evidence_date'] == record['recent_evidence_date']
        assert brief['suitability'] == record['editorial']['suitability']
        assert brief['year'] == record['dates']['reference_year']
        assert brief['decade'] == record['dates']['decade']
        assert record['dates']['decade'] == f"{record['dates']['reference_year'] // 10 * 10}s"
        assert record['evidence'], 'Missing evidence'
        for claim in record['evidence']:
            assert claim['source_id'] in sources, 'Dangling source'
            assert sources[claim['source_id']]['read_method'] != 'search_excerpt', 'Excerpt in checked corpus'
        assert record['popularity'] == {'current_status': 'not_measured', 'snapshots': []}, 'Unmeasured heat changed'
        assert not record['rights']['third_party_media_included'], 'Unreviewed media inclusion'
        assert record['editorial']['is_editorial_interpretation'] is True
    from datetime import date
    def key(r):
        value = r['recent_evidence_date'] or str(r['dates']['reference_year'])
        return int(value.replace('-', '').ljust(8, '0'))
    assert [key(r) for r in pack['records']] == sorted([key(r) for r in pack['records']], reverse=True), 'Oldest-first export'
    for record in pack['records']:
        value = record['recent_evidence_date']
        if value:
            parts = [int(x) for x in value.split('-')]
            observed = date(parts[0], parts[1] if len(parts)>1 else 1, parts[2] if len(parts)>2 else 1)
            assert observed <= date.fromisoformat(json.loads((ROOT / '知识库/收集范围.json').read_text())['as_of']), 'Future evidence date'
        assert record['categories'] and set(record['categories']) <= {'hotword', 'meme', 'slang'}
    demo = json.loads((ROOT / 'examples/knowledge-to-copy.json').read_text(encoding='utf-8'))
    assert all((ROOT / '知识库/条目' / (d['entry_id'] + '.md')).exists() for d in demo['examples']), 'Unknown demo parent'
    config = json.loads((ROOT / 'create-funny-meme-cards/assets/brand.example.json').read_text(encoding='utf-8'))
    assert config['brand']['qr_path'] is None and config['brand']['logo_path'] is None
    assert config['data_dir'] is None and config['project_credit']['author'] == '秋哥'
    summary = json.loads((ROOT / 'docs/阶段交付清单.json').read_text(encoding='utf-8'))
    assert summary['record_count'] == len(ids)
    assert summary['source_count'] == len(sources)
    assert summary['decade_counts'] == dict(Counter(r['dates']['decade'] for r in pack['records']))
    assert summary['language_counts'] == dict(Counter(r['language'] for r in pack['records']))
    assert not set(ids).intersection(b['id'] for b in pack['backlog'])
    html = (ROOT / '预览.html').read_text(encoding='utf-8')
    embedded = re.search(r'<script id="knowledge-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    assert json.loads(embedded) == pack, 'Preview data is stale'
    embedded_focus = re.search(r'<script id="focus-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    focus = json.loads((path / 'focus.json').read_text(encoding='utf-8'))
    assert json.loads(embedded_focus) == focus
    assert summary['recent_record_count'] == sum(int((r['recent_evidence_date'] or str(r['dates']['reference_year']))[:4]) in focus['priority_years'] for r in pack['records'])
    assert (ROOT / 'preview.js').read_text(encoding='utf-8').strip() in html, 'Preview JS is stale'
    for md in ROOT.rglob('*.md'):
        if any(x in md.relative_to(ROOT).parts for x in ['.venv', '私人', '采集收件箱', '.git']):
            continue
        for target in re.findall(r'\]\(([^)]+)\)', md.read_text(encoding='utf-8')):
            if not target.startswith(('http://', 'https://', '#')):
                assert (md.parent / target.split('#')[0].split('?')[0]).exists(), f'Missing local link: {target}'
    studio = ROOT / 'create-funny-meme-cards/assets/poster-studio'
    import hashlib
    approved_media = {}
    manifest = json.loads((studio / 'samples.json').read_text())
    assert manifest['private_brand_included'] is False
    for sample in manifest['samples']:
        asset = studio / sample['path']
        assert hashlib.sha256(asset.read_bytes()).hexdigest() == sample['sha256'], 'Sample changed without review'
        approved_media[asset] = sample['sha256']
    assert len(approved_media) == 4
    icon_meta = json.loads((ROOT / 'pwa/icons/assets.json').read_text())
    import struct
    for name, checksum in icon_meta['files'].items():
        asset = ROOT / 'pwa/icons' / name
        assert hashlib.sha256(asset.read_bytes()).hexdigest() == checksum
        if asset.suffix == '.png':
            assert asset.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            size = 192 if name=='icon-192.png' else (512 if name=='icon-512.png' else 180)
            assert struct.unpack('>II',asset.read_bytes()[16:24]) == (size,size)
            approved_media[asset] = checksum
    manifest = json.loads((ROOT / 'manifest.webmanifest').read_text())
    assert manifest['display']=='standalone' and manifest['start_url']=='./app.html'
    shell = json.loads((ROOT / 'pwa-shell.json').read_text())
    assert shell['private_api_cached'] is False
    for name, checksum in shell['public_resources'].items():
        assert not any(x in name for x in ['api/', '私人/', '采集收件箱/', '.local.'])
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == checksum, 'Stale PWA asset: '+name
    styles = json.loads((studio / 'styles.json').read_text())
    assert {s['id'] for s in styles} == {'comic', 'pets', 'retro', 'collection'}
    assert (studio / 'styles.js').read_text() == 'window.MEME_STYLES = ' + json.dumps(styles, ensure_ascii=False, indent=2) + ';\n'
    import base64
    images = {s['id']: 'data:image/png;base64,' + base64.b64encode((studio / s['sample']).read_bytes()).decode() for s in styles}
    assert (studio / 'samples.js').read_text() == 'window.MEME_SAMPLE_IMAGES = ' + json.dumps(images) + ';\n'
    vendors = json.loads((studio / 'vendor/sources.json').read_text())
    for vendor in vendors['files']:
        assert hashlib.sha256((studio / 'vendor' / vendor['file']).read_bytes()).hexdigest() == vendor['sha256']
    studio_html = (studio / 'index.html').read_text()
    for resource in re.findall(r'(?:src|href)="([^"]+)"', studio_html):
        if not resource.startswith(('http:', 'https:', '#')):
            assert (studio / resource).exists(), f'Missing studio resource: {resource}'
    # Scan for copied private assets, personal Library references, local account paths and credentials.
    forbidden = [r'libfile_' + r'[a-z0-9]+', r'/Users/' + r'[A-Za-z0-9_]+/', r'qiugo-' + r'qr', r'brand-' + r'footer\.png']
    for file in ROOT.rglob('*'):
        if not file.is_file() or file.name == 'validate_package.py' or any(x in file.relative_to(ROOT).parts for x in ['.git', '.venv', '.obsidian', '__pycache__', 'private', '私人', 'runtime', 'outputs', '采集收件箱']):
            continue
        if file in approved_media:
            continue
        assert file.suffix not in ['.png', '.jpg', '.jpeg', '.mp3', '.mp4'], f'Unregistered media in public preview: {file.name}'
        text = file.read_text(encoding='utf-8')
        assert not any(re.search(p, text) for p in forbidden), f'Private reference in {file.name}'
    return {'status': 'passed', 'records': len(ids), 'sources': len(sources), 'backlog_groups': len(pack['backlog']), 'decades': summary['decade_counts']}

if __name__ == '__main__':
    print(json.dumps(validate(), ensure_ascii=False, indent=2))
