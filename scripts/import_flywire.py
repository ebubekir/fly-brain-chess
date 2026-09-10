"""Reproduce a compact, provenance-tracked induced subgraph of FAFB v783."""
import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
import urllib.request

BASE = 'https://storage.googleapis.com/flywire-data/codex/data/fafb/783/'
ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def rows(path):
    with gzip.open(path, 'rt') as stream:
        yield from csv.DictReader(stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', type=int, default=256)
    parser.add_argument('--neuropil', default='PB')
    args = parser.parse_args()
    raw = ROOT / 'data/raw'
    raw.mkdir(parents=True, exist_ok=True)
    sources = []
    for name in ['connections', 'neurons']:
        path = raw / f'{name}.csv.gz'
        url = BASE + path.name
        if not path.exists():
            temporary = path.with_suffix('.download')
            urllib.request.urlretrieve(url, temporary)
            temporary.replace(path)
        sources.append({'url': url, 'sha256': sha256(path)})
    neurons = {r['root_id']: r for r in rows(raw / 'neurons.csv.gz')}
    # Keep fast transmitter classes only. GLU inhibitory sign is an explicit
    # simplifying assumption, not receptor-specific evidence for every synapse.
    eligible = {rid for rid, n in neurons.items() if n['nt_type'] in {'ACH', 'GABA', 'GLUT'}}
    degree = Counter()
    for row in rows(raw / 'connections.csv.gz'):
        a, b = row['pre_root_id'], row['post_root_id']
        if row['neuropil'] == args.neuropil and a in eligible and b in eligible and a != b:
            degree[a] += int(row['syn_count'])
            degree[b] += int(row['syn_count'])
    selected = sorted(sorted(degree, key=lambda n: (-degree[n], n))[:args.size])
    if len(selected) != args.size:
        raise ValueError(f'Only {len(selected)} eligible neurons found')
    selected_set = set(selected)
    counts = Counter()
    regions = {}
    for row in rows(raw / 'connections.csv.gz'):
        pair = row['pre_root_id'], row['post_root_id']
        if pair[0] in selected_set and pair[1] in selected_set and pair[0] != pair[1]:
            counts[pair] += int(row['syn_count'])
            regions.setdefault(pair, set()).add(row['neuropil'])
    data = {
        'provenance': {
            'dataset': 'FlyWire FAFB', 'release': '783', 'license': 'CC-BY-NC-4.0',
            'license_url': 'https://flywire.ai/guidelines', 'sources': sources,
            'citation': 'https://doi.org/10.1038/s41586-024-07558-y',
            'selection': f'Top {args.size} ACH/GABA/GLUT neurons by incident synapse count in {args.neuropil}; ties by root ID. Induced directed graph across ALL neuropils in the downloaded table; aggregate parallel rows; omit self-loops. Missing/below-release-threshold edges are not reconstructed.',
            'coordinates': 'Seeded spring layout; synthetic visualization, not anatomical positions',
            'sign_rule': 'ACH +1; GABA and GLUT -1; predicted transmitter labels, simplified receptor-independent assumption',
        },
        'nodes': [{'root_id': rid, 'nt_type': neurons[rid]['nt_type'], 'nt_type_score': float(neurons[rid]['nt_type_score'])} for rid in selected],
        'edges': [{'pre_root_id': a, 'post_root_id': b, 'syn_count': count, 'neuropils': sorted(regions[(a,b)])} for (a,b), count in sorted(counts.items())],
    }
    out = ROOT / 'backend/data/flywire_783.json'
    out.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({'nodes': len(selected), 'edges': len(counts), 'transmitters': dict(Counter(n['nt_type'] for n in data['nodes'])), 'sha256': sha256(out)}, indent=2))


if __name__ == '__main__':
    main()
