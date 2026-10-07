"""Export all ranked categories, notes, and photo metadata with one login."""
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import parse_qsl, urljoin, urlsplit

from probe import API, Client, business, rows, save


def fetch_pages(client, path, params, directory, label):
    """Keep every response and follow only same-endpoint pagination."""
    collected, seen_pages = [], set()
    expected = None
    for page in range(1, 1001):
        key = json.dumps(params, sort_keys=True)
        if key in seen_pages:
            raise RuntimeError(f'{label}: pagination repeated; saved pages retained.')
        seen_pages.add(key)
        payload = client.request(path, params)
        save(directory, f'{label}-page-{page:03}.json', payload)
        batch = payload.get('results') if isinstance(payload, dict) else payload
        if not isinstance(batch, list) or any(not isinstance(r, dict) for r in batch):
            raise RuntimeError(f'{label}: unexpected response shape; raw response saved.')
        collected.extend(batch)
        if isinstance(payload, dict) and isinstance(payload.get('count'), int):
            expected = payload['count']
        next_page = payload.get('next') if isinstance(payload, dict) else None
        if not next_page:
            if expected is not None and expected != len(collected):
                raise RuntimeError(f'{label}: received {len(collected)} rows but server reports {expected}.')
            return collected
        target = urlsplit(urljoin(API + path, next_page))
        if target.scheme != 'https' or target.netloc != urlsplit(API).netloc or target.path != path:
            raise RuntimeError(f'{label}: unexpected pagination destination; stopped.')
        params = dict(parse_qsl(target.query))
    raise RuntimeError(f'{label}: exceeded pagination limit.')


def own_records(records, uid, label, warnings):
    accepted, rejected, unspecified = [], 0, 0
    for row in records:
        owner = row.get('user', row.get('user_id'))
        if isinstance(owner, dict):
            owner = owner.get('id')
        if owner is not None and str(owner) != uid:
            rejected += 1
            continue
        if owner is None:
            unspecified += 1
        accepted.append(row)
    if rejected:
        warnings.append(f'{label}: excluded {rejected} records belonging to other users from combined data.')
    if unspecified:
        warnings.append(f'{label}: {unspecified} records have no owner field; retained as returned by scoped request.')
    return accepted


def make_entries(rankings, notes, photos):
    by_notes, by_photos = {}, {}
    for collection, index in ((notes, by_notes), (photos, by_photos)):
        for record in collection:
            bid, _ = business(record)
            index.setdefault(str(bid), []).append(record)
    entries = []
    for category, records in rankings.items():
        for position, record in enumerate(records, 1):
            bid, name = business(record)
            entries.append({
                'category': category, 'api_position': position,
                'business_id': bid, 'name': name, 'score': record.get('score'),
                'ranking_value': record.get('value'), 'ranking': record,
                'notes': by_notes.get(str(bid), []),
                'photos': by_photos.get(str(bid), []),
            })
    return entries


def main():
    if not sys.stdin.isatty():
        raise RuntimeError('Run this in your terminal so login stays local.')
    os.umask(0o077)
    print('Export all Beli categories, notes, and photo links. No ranking changes.')
    client = Client()
    identifier = input('Beli email or international phone number: ').strip()
    password = getpass.getpass('Beli password (hidden): ')
    field = 'email' if '@' in identifier else 'phone_no'
    tokens = client.request('/api/token/', login={field: identifier, 'password': password})
    del password
    client.token = tokens['access']
    del tokens
    profiles = rows(client.request('/api/user/logged-in/'))
    if len(profiles) != 1 or not isinstance(profiles[0], dict):
        raise RuntimeError('Unexpected profile response.')
    uid = str(profiles[0]['id'])
    print('Authenticated as', profiles[0].get('username', '(unknown)'))
    del profiles
    root = Path(__file__).resolve().parent / 'data'
    root.mkdir(exist_ok=True, mode=0o700)
    directory = Path(tempfile.mkdtemp(prefix='export-' + datetime.now().strftime('%Y%m%d-'), dir=root))
    raw = directory / 'raw'
    raw.mkdir(mode=0o700)
    print('Saving export to', directory, flush=True)
    warnings, errors, rankings = [], {}, {}
    notes, photos, scores = [], [], []
    try:
        scores = own_records(fetch_pages(client, f'/api/user-scores/{uid}/', None, raw, 'scores'), uid, 'scores', warnings)
        categories = sorted({r['category'] for r in scores if r.get('category')})
        if not categories or any(not re.fullmatch('[A-Z_]{3,20}', c) for c in categories):
            raise RuntimeError('Could not discover valid category codes from scores.')
        print('Found categories:', ', '.join(categories), flush=True)
    except (RuntimeError, ValueError, KeyError) as error:
        errors['category_discovery'] = str(error)
        categories = ['RES', 'BAR', 'COFFEE', 'BAKERY', 'DESSERT']
        warnings.append('Category discovery failed; using documented fallback codes. Verify coverage in the app.')
    if len(categories) < 5:
        warnings.append('Fewer than five populated categories found in scores. Verify against the app before treating this as complete.')
    for category in categories:
        try:
            records = own_records(fetch_pages(client, '/api/get-ranking/', {'user': uid, 'category': category}, raw, 'rankings-' + category), uid, category, warnings)
            if any(r.get('category') != category for r in records):
                raise RuntimeError('Response category does not match request; raw data saved.')
            ids = [r.get('id') for r in records]
            if len(set(ids)) != len(ids):
                warnings.append(f'{category}: repeated ranking IDs; review raw pagination.')
            rankings[category] = records
            print(f'{category}: {len(records)} rankings', flush=True)
        except (RuntimeError, ValueError, KeyError) as error:
            errors[category] = str(error)
            print(f'{category}: {error}', flush=True)
    collections = {}
    for label, path, params in [
        ('notes', '/api/datauserbusinesstext-sparse/', {'user': uid, 'field__name': 'NOTES'}),
        ('photos', '/api/user-business-photos/', {'user': uid}),
    ]:
        try:
            records = own_records(fetch_pages(client, path, params, raw, label), uid, label, warnings)
            collections[label] = records
            print(f'{label}: {len(records)} records', flush=True)
        except (RuntimeError, ValueError, KeyError) as error:
            errors[label] = str(error)
            print(f'{label}: {error}', flush=True)
    notes, photos = collections.get('notes', []), collections.get('photos', [])
    expected = {(r.get('category'), str(business(r)[0])) for r in scores}
    actual = {(c, str(business(r)[0])) for c, records in rankings.items() for r in records}
    missing = expected - actual
    if missing:
        warnings.append(f'{len(missing)} category/place pairs from scores are missing from rankings.')
    result = {
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'rankings_by_category': rankings, 'scores': scores,
        'notes': notes, 'photos': photos,
        'entries': make_entries(rankings, notes, photos),
    }
    save(directory, 'export.json', result)
    report = {
        'status': 'needs_review' if errors or warnings else 'retrieved_pending_app_verification',
        'counts_by_category': {c: len(r) for c, r in rankings.items()},
        'total_rankings': sum(map(len, rankings.values())),
        'notes': len(notes), 'photos': len(photos), 'errors': errors, 'warnings': warnings,
        'missing_score_pairs': sorted(missing, key=str),
        'limitations': [
            'Photo URLs and metadata saved; image files have not been downloaded.',
            'Visit dates embedded in ranking records preserved; per-place visit endpoint not queried.',
            'api_position preserves response order, not an independently verified exact rank.',
            'Compare category totals, sample notes, and photos with the app to verify completeness.',
        ],
    }
    save(directory, 'report.json', report)
    print(f"\nSaved {report['total_rankings']} rankings, {len(notes)} notes, {len(photos)} photo records.")
    print('Result:', directory / 'export.json')
    for warning in warnings:
        print('Review:', warning)
    if errors:
        print('Some requests failed. See report.json; successful data has been preserved.')
        return 1
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled. Any saved raw pages remain on disk.')
        sys.exit(1)
    except (RuntimeError, ValueError, KeyError, OSError) as error:
        print(f'Export stopped: {error}', file=sys.stderr)
        sys.exit(1)
