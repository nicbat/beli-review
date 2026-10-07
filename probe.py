"""Small interactive, read-only Beli export probe. Standard library only."""
import getpass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

API = 'https://backoffice-service-t57o3dxfca-nn.a.run.app'
AUTH = 'https://backoffice-service-onboarding-t57o3dxfca-nn.a.run.app'
READS = (
    r'/api/user/logged-in/', r'/api/get-ranking/',
    r'/api/user-scores/[0-9a-f-]+/',
    r'/api/datauserbusinesstext-sparse/', r'/api/user-business-photos/',
    r'/api/visit-dates-on-business/[0-9a-f-]+/[0-9]+/',
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self):
        self.opener = build_opener(NoRedirect())
        self.token = None
        self.last_request = 0

    def request(self, path, params=None, login=None):
        if login is not None:
            if path != '/api/token/':
                raise ValueError('Only login may write.')
            host = AUTH
        else:
            if not any(re.fullmatch(pattern, path) for pattern in READS):
                raise ValueError('Endpoint not in read allowlist.')
            host = AUTH if path == '/api/user/logged-in/' else API
        time.sleep(max(0, 0.4 - (time.monotonic() - self.last_request)))
        headers = {
            'Accept': 'application/json', 'Origin': 'capacitor://localhost',
            'User-Agent': 'Mozilla/5.0',
        }
        if self.token and login is None:
            headers['Authorization'] = 'Bearer ' + self.token
        body = None
        if login is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(login).encode()
        url = host + path + ('?' + urlencode(params) if params else '')
        request = Request(url, data=body, headers=headers)
        self.last_request = time.monotonic()
        try:
            with self.opener.open(request, timeout=45) as response:
                return json.load(response)
        except HTTPError as error:
            # Do not print response bodies: they may contain personal data.
            raise RuntimeError(f'HTTP {error.code} at {path}; response body withheld.') from None
        except URLError:
            raise RuntimeError(f'Connection failed at {path}.') from None


def rows(payload):
    value = payload.get('results', payload) if isinstance(payload, dict) else payload
    return value if isinstance(value, list) else [value] if isinstance(value, dict) else []


def business(record):
    value = record.get('business', record.get('business_id'))
    if isinstance(value, dict):
        return value.get('id'), value.get('name', '')
    return value, record.get('name', '')


def save(directory, filename, payload):
    with (directory / filename).open('x', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def describe(payload):
    records = rows(payload)
    return {
        'returned_rows': len(records),
        'reported_count': payload.get('count') if isinstance(payload, dict) else None,
        'has_next_page': bool(payload.get('next')) if isinstance(payload, dict) else False,
        'first_record_fields': sorted(records[0]) if records and isinstance(records[0], dict) else [],
    }


def main():
    if not sys.stdin.isatty():
        raise RuntimeError('Run this interactively in your own terminal.')
    os.umask(0o077)
    client = Client()
    print('Beli read-only probe. Credentials stay in memory. Ctrl+C cancels.')
    identifier = input('Beli email or international phone number: ').strip()
    password = getpass.getpass('Beli password (hidden): ')
    field = 'email' if '@' in identifier else 'phone_no'
    tokens = client.request('/api/token/', login={field: identifier, 'password': password})
    del password
    client.token = tokens['access']
    del tokens
    profiles = rows(client.request('/api/user/logged-in/'))
    if len(profiles) != 1 or not isinstance(profiles[0], dict):
        raise RuntimeError('Unexpected profile shape; no account data saved.')
    uid = str(profiles[0]['id'])
    print('Authenticated as', profiles[0].get('username', '(username unavailable)'))
    del profiles
    category = input('Category code (RES restaurants; enter RES if unsure): ').strip().upper() or 'RES'
    if not re.fullmatch('[A-Z_]{3,20}', category):
        raise RuntimeError('Expected an uppercase category code.')
    root = Path(__file__).resolve().parent / 'data'
    root.mkdir(exist_ok=True, mode=0o700)
    directory = Path(tempfile.mkdtemp(prefix='probe-', dir=root))
    print('Saving this test to', directory)
    rankings = client.request('/api/get-ranking/', {'user': uid, 'category': category})
    save(directory, 'rankings.json', rankings)
    print('Rankings:', json.dumps(describe(rankings)))
    candidates = [r for r in rows(rankings) if isinstance(r, dict)]
    query = input('Part of the restaurant name to test: ').strip().casefold()
    matches = [r for r in candidates if query in str(business(r)[1]).casefold()]
    for index, record in enumerate(matches, 1):
        bid, name = business(record)
        print(f'{index}. {name} (business ID {bid})')
    if not matches:
        print('No named matches. Rankings saved for response-shape inspection.')
        return
    choice = int(input('Choose the number: '))
    if not 1 <= choice <= len(matches):
        raise RuntimeError('Selection outside the list.')
    selected = matches[choice - 1]
    bid, name = business(selected)
    if not str(bid).isdigit():
        raise RuntimeError('Unexpected business ID shape.')
    save(directory, 'selected-restaurant.json', selected)
    report = {'category': category, 'business_id': bid, 'name': name, 'checks': {}}
    checks = [
        ('notes', '/api/datauserbusinesstext-sparse/', {'user': uid, 'business': bid, 'field__name': 'NOTES'}),
        ('photos', '/api/user-business-photos/', {'user': uid, 'business': bid}),
        ('visits', f'/api/visit-dates-on-business/{uid}/{bid}/', None),
    ]
    for label, path, params in checks:
        try:
            payload = client.request(path, params)
            save(directory, label + '.json', payload)
            report['checks'][label] = describe(payload)
            # Filters may be ignored; do not interpret a nonempty list as a match.
            report['checks'][label]['matching_business_rows'] = sum(
                str(business(r)[0]) == str(bid) for r in rows(payload) if isinstance(r, dict)
            )
            print(label + ':', json.dumps(report['checks'][label]))
        except (RuntimeError, ValueError) as error:
            report['checks'][label] = {'error': str(error)}
            print(label + ':', str(error))
    save(directory, 'report.json', report)
    print('Done. Responses saved; completeness and image download still need verification.')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.')
    except (RuntimeError, ValueError, KeyError, OSError) as error:
        print(f'Probe stopped: {error}', file=sys.stderr)
        sys.exit(1)
