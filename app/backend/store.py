"""Transactional local workspace. Source exports are immutable; decisions are versioned."""
from contextlib import contextmanager, closing
import hashlib
import heapq
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

CATEGORIES = {'RES': 'Restaurants', 'COF': 'Coffee', 'BAK': 'Bakeries', 'DES': 'Desserts', 'BAR': 'Bars'}
BANDS = ['Favorites', 'Very good', 'Good', 'Fine', "Didn't like", 'Bad']


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def key(category, business_id):
    return f'{category}:{business_id}'


def initial():
    return dict(account=None, original=None, latest=None, sources=[], order={}, places={},
                bands={c: BANDS[:] for c in CATEGORIES}, comparisons=[], sessions={}, issues=[], moves=[])


def normalize(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('rankings_by_category'), dict):
        raise ValueError('Choose a Beli export.json containing rankings_by_category.')
    entries, orders, owners = {}, {}, set()
    notes, photos = payload.get('notes', []), payload.get('photos', [])
    for label, rows in [('notes', notes), ('photos', photos)]:
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError(f'Invalid {label} collection.')
        ids = [r.get('id') for r in rows]
        if any(i is None for i in ids) or len(ids) != len(set(ids)):
            raise ValueError(f'Duplicate or missing {label} IDs.')
        for r in rows:
            if label == 'notes' and r.get('value') is not None and not isinstance(r['value'], str):
                raise ValueError('Written notes must contain text.')
            if label == 'photos' and any(r.get(field) is not None and not isinstance(r[field], str) for field in ('image','thumbnail','description')):
                raise ValueError('Photo URLs and captions must contain text.')
            owner = r.get('user')
            if isinstance(owner, dict):
                owner = owner.get('id')
            if owner is not None:
                owners.add(str(owner))
    for category, rows in payload['rankings_by_category'].items():
        if not isinstance(rows, list) or not category:
            raise ValueError('Invalid category rankings.')
        orders[category] = []
        for position, row in enumerate(rows, 1):
            if not isinstance(row, dict) or not isinstance(row.get('business'), dict):
                raise ValueError('Ranking is missing business details.')
            business = row['business']
            bid = business.get('id')
            if type(bid) is not int or not isinstance(business.get('name'), str) or not business['name']:
                raise ValueError('Ranking is missing a business ID or name.')
            if any(business.get(field) is not None and not isinstance(business[field], str) for field in ('city','country')):
                raise ValueError('Business locations must contain text.')
            cuisines = business.get('cuisines')
            if cuisines is not None and (not isinstance(cuisines, list) or any(not isinstance(item, str) for item in cuisines)):
                raise ValueError('Cuisine tags must be a list of text values.')
            for field in ('score','value'):
                value = row.get(field)
                if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):
                    raise ValueError('Ranking scores must be finite numbers.')
            k = key(category, bid)
            if k in entries:
                raise ValueError('Duplicate business/category membership.')
            owner = row.get('user')
            if isinstance(owner, dict):
                owner = owner.get('id')
            if owner is not None:
                owners.add(str(owner))
            def attached(r):
                b = r.get('business')
                return (b.get('id') if isinstance(b, dict) else b) == bid
            entries[k] = dict(key=k, category=category, business_id=bid,
                              name=business['name'], business=business, position=position,
                              score=row.get('score'), ranking_value=row.get('value'),
                              visit_dates=row.get('visit_dates', []), created_dt=row.get('created_dt'),
                              notes=[n for n in notes if attached(n)], photos=[p for p in photos if attached(p)])
            orders[category].append(k)
    if len(owners) != 1:
        raise ValueError('Export must identify exactly one account across rankings and attachments.')
    stamp = payload.get('exported_at')
    try:
        parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        stamp = parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, AttributeError):
        raise ValueError('Export must include an exported_at timestamp with a timezone.')
    return dict(account=owners.pop(), entries=entries, order=orders, exported_at=stamp)


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, hash TEXT UNIQUE NOT NULL, imported_at TEXT NOT NULL, data TEXT NOT NULL, normalized TEXT NOT NULL, report TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, created_at TEXT NOT NULL, label TEXT NOT NULL, before_state TEXT NOT NULL, after_state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS checkpoints (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, name TEXT NOT NULL, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS undo_stack (id INTEGER PRIMARY KEY, operation_id TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0);
            PRAGMA user_version=1;
            ''')
            db.execute('INSERT OR IGNORE INTO workspace VALUES (1,0,?)', (encode(initial()),))
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def read(self, db):
        row = db.execute('SELECT * FROM workspace WHERE id=1').fetchone()
        return row['revision'], json.loads(row['data'])

    def source(self, db, sid):
        if not sid:
            return dict(entries={}, order={}, exported_at='')
        row = db.execute('SELECT normalized FROM imports WHERE id=?', (sid,)).fetchone()
        return json.loads(row[0])

    def entries(self, db, state):
        entries = {}
        # Sources are chronological; older imports never replace newer source content.
        for sid in state['sources']:
            for k, current in self.source(db, sid)['entries'].items():
                previous = entries.get(k, {})
                for field in ('notes','photos'):
                    history = previous.get('previous_' + field, []) + previous.get(field, [])
                    present = {str(item.get('id')) for item in current[field]}
                    current['previous_' + field] = list({str(item.get('id')):item for item in history if str(item.get('id')) not in present}.values())
                entries[k] = current
        return entries

    def view(self):
        with self.connect() as db:
            revision, s = self.read(db)
            entries = self.entries(db, s)
            for k, e in entries.items():
                e['flags'] = dict(no_photos=not e['photos'],
                                  no_note=not any(str(n.get('value') or '').strip() for n in e['notes']),
                                  missing_caption=any(not str(p.get('description') or '').strip() for p in e['photos']))
            snapshots = [dict(id=r['id'], imported_at=r['imported_at'],
                              exported_at=json.loads(r['normalized'])['exported_at'],
                              count=len(json.loads(r['normalized'])['entries']))
                         for r in db.execute('SELECT * FROM imports ORDER BY imported_at DESC')]
            history = [dict(r) for r in db.execute('SELECT id,revision,created_at,label FROM operations ORDER BY revision DESC LIMIT 100')]
            checkpoints = [dict(id=r['id'], created_at=r['created_at'], name=r['name'], order=json.loads(r['state'])['order']) for r in db.execute('SELECT * FROM checkpoints ORDER BY created_at DESC')]
            undo = db.execute('SELECT COUNT(*) FROM undo_stack WHERE undone=0').fetchone()[0]
            redo = db.execute('SELECT COUNT(*) FROM undo_stack WHERE undone=1').fetchone()[0]
            return dict(revision=revision, state=s, entries=entries, categories=CATEGORIES,
                        original=self.source(db, s['original'])['order'],
                        latest=self.source(db, s['latest'])['order'], imports=snapshots,
                        history=history, checkpoints=checkpoints, can_undo=bool(undo), can_redo=bool(redo))

    def preview(self, payload, report=None):
        normalized = normalize(payload)
        with self.connect() as db:
            _, s = self.read(db)
            return self._preview(db, s, payload, normalized, report or {})

    def _preview(self, db, s, payload, n, report):
        if s['account'] and s['account'] != n['account']:
            raise ValueError('This export belongs to another account. Use a separate workspace.')
        digest = hashlib.sha256(encode(payload).encode()).hexdigest()
        duplicate = db.execute('SELECT id FROM imports WHERE hash=?', (digest,)).fetchone()
        old = self.source(db, s['latest'])
        oldkeys, newkeys = set(old['entries']), set(n['entries'])
        changes = [k for k in oldkeys & newkeys if old['entries'][k] != n['entries'][k]]
        added, missing = sorted(newkeys-oldkeys), sorted(oldkeys-newkeys)
        transfers = [k for k in added if any(old['entries'][o]['business_id'] == n['entries'][k]['business_id'] for o in missing)]
        return dict(hash=digest, duplicate=bool(duplicate), older=bool(s['latest'] and n['exported_at'] < old['exported_at']),
                    exported_at=n['exported_at'], count=len(newkeys), added=added, missing=missing,
                    changed=sorted(changes), transfers=transfers,
                    names={k:e['name'] for k,e in {**old['entries'], **n['entries']}.items()},
                    warnings=report.get('warnings', []), errors=report.get('errors', {}))

    def mutate(self, request):
        opid = request.get('operation_id')
        if not isinstance(opid, str) or len(opid) > 100:
            raise ValueError('An operation ID is required.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM operations WHERE id=?', (opid,)).fetchone():
                return {'ok': True, 'duplicate': True}
            rev, s = self.read(db)
            if request.get('revision') != rev:
                raise Conflict('This workspace changed in another tab. Reload the latest state before trying again.')
            before = encode(s)
            action = request.get('action')
            label = self.apply(db, s, action, request)
            after = encode(s)
            db.execute('UPDATE workspace SET revision=?,data=? WHERE id=1', (rev+1, after))
            db.execute('INSERT INTO operations VALUES (?,?,?,?,?,?)', (opid, rev+1, now(), label, before, after))
            if action not in ('undo', 'redo', 'checkpoint'):
                db.execute('DELETE FROM undo_stack WHERE undone=1')
                db.execute('INSERT INTO undo_stack(operation_id) VALUES (?)', (opid,))
        return {'ok': True}

    def checkpoint(self, db, s, name):
        db.execute('INSERT INTO checkpoints VALUES (?,?,?,?)', (str(uuid.uuid4()), now(), name[:160], encode(s)))

    def apply(self, db, s, action, r):
        if action == 'import':
            payload, report = r['payload'], r.get('report') or {}
            n = normalize(payload)
            p = self._preview(db, s, payload, n, report)
            if p['duplicate']:
                raise ValueError('This export is already archived. Use redo or restore a checkpoint to recover an undone import.')
            sid = str(uuid.uuid4())
            self.checkpoint(db, s, 'Before import')
            db.execute('INSERT INTO imports VALUES (?,?,?,?,?,?)', (sid, p['hash'], now(), encode(payload), encode(n), encode(report)))
            if p['older']:
                return 'Archived older export'
            first = not s['original']
            s['account'] = n['account']
            s['original'] = s['original'] or sid
            s['latest'] = sid
            s['sources'].append(sid)
            for c, order in n['order'].items():
                s['order'].setdefault(c, [])
                s['bands'].setdefault(c, BANDS[:])
                for k in order:
                    if k not in s['places']:
                        s['order'][c].append(k)
                        s['places'][k] = dict(band=None, reference=False, status='unreviewed' if first else 'new',
                                              attention=False, reason='', excluded=False, missing=False)
                    s['places'][k]['missing'] = False
            for k in p['missing']:
                s['places'][k]['missing'] = True
            for kind, keys in [('missing', p['missing']), ('category', p['transfers'])]:
                for k in keys:
                    s['issues'].append(dict(id=str(uuid.uuid4()), kind=kind, key=k, source=sid, resolved=False))
            if not first and p['changed']:
                s['issues'].append(dict(id=str(uuid.uuid4()), kind='source_changes', keys=p['changed'], source=sid, resolved=False))
            # Preserve completed answers but restart a prompt if its subject is now missing.
            for c, session in s['sessions'].items():
                # Integrate additions without losing the saved session's original baseline.
                seed = session['proposal'] + [k for k in s['order'][c] if k not in session['proposal']]
                session['proposal'] = self.ordered(seed, s['comparisons'], c)
                if session.get('pair') and any(s['places'][k]['missing'] for k in session['pair']):
                    session['pair'] = None
                    session['notice'] = 'A place in this comparison is absent from the latest export. Choose another session after reviewing the import.'
            return f'Imported {len(n["entries"])} places'
        if action in ('undo', 'redo'):
            query = ('SELECT * FROM undo_stack WHERE undone=0 ORDER BY id DESC LIMIT 1' if action == 'undo'
                     else 'SELECT * FROM undo_stack WHERE undone=1 ORDER BY id ASC LIMIT 1')
            row = db.execute(query).fetchone()
            if not row:
                raise ValueError(f'Nothing to {action}.')
            op = db.execute('SELECT * FROM operations WHERE id=?', (row['operation_id'],)).fetchone()
            restored = json.loads(op['before_state' if action == 'undo' else 'after_state'])
            s.clear(); s.update(restored)
            db.execute('UPDATE undo_stack SET undone=? WHERE id=?', (action == 'undo', row['id']))
            return f'{action.title()}: {op["label"]}'
        if action == 'checkpoint':
            self.checkpoint(db, s, r.get('name') or 'Saved checkpoint')
            return 'Saved checkpoint'
        if action == 'restore':
            row = db.execute('SELECT state FROM checkpoints WHERE id=?', (r['id'],)).fetchone()
            if not row:
                raise ValueError('Checkpoint not found.')
            self.checkpoint(db, s, 'Before checkpoint restore')
            restored = json.loads(row['state'])
            s.clear(); s.update(restored)
            return 'Restored checkpoint'
        if action == 'resolve':
            issue = next((i for i in s['issues'] if i['id'] == r['id']), None)
            if not issue:
                raise ValueError('Import issue not found.')
            issue['resolved'] = True
            return 'Acknowledged import difference'
        c = r.get('category', 'RES')
        if c not in s['order']:
            raise ValueError('Import this category first.')
        if action == 'bands':
            bands = [str(b).strip() for b in r['bands']]
            if not bands or len(bands) > 10 or any(not b or len(b)>60 for b in bands) or len(set(bands)) != len(bands):
                raise ValueError('Use 1–10 different, nonempty band names (up to 60 characters).')
            old = s['bands'][c]
            renames = r.get('renames')
            if renames is not None and (not isinstance(renames, dict) or any(name not in old or replacement not in bands for name,replacement in renames.items())):
                raise ValueError('Band renames must map existing names to new names.')
            for k in s['order'][c]:
                band = s['places'][k]['band']
                if band in old:
                    if renames is not None:
                        replacement = renames.get(band, band)
                        s['places'][k]['band'] = replacement if replacement in bands else None
                    else:
                        index = old.index(band)
                        s['places'][k]['band'] = bands[index] if index < len(bands) else None
            if renames is not None:
                for suggestion in s['sessions'].get(c, {}).get('band_suggestions', []):
                    suggestion['band'] = renames.get(suggestion['band'], suggestion['band'])
            s['bands'][c] = bands
            return 'Edited quality bands'
        if action in ('place', 'move'):
            k = r['key']
            if k not in s['places'] or k not in s['order'][c]:
                raise ValueError('Place not in this category.')
            p = s['places'][k]
            if action == 'move':
                if s['sessions'].get(c, {}).get('status') == 'active':
                    raise ValueError('Finish the current session before a manual move.')
                anchor = r['anchor']
                if anchor not in s['order'][c] or anchor == k:
                    raise ValueError('Choose another place in this category.')
                s['order'][c].remove(k)
                idx = s['order'][c].index(anchor) + (r.get('side') == 'after')
                s['order'][c].insert(idx, k)
                p['status'] = 'reviewed'
                positions = {member:i for i,member in enumerate(s['order'][c])}
                for decision in s['comparisons']:
                    if decision['category'] == c and decision['active'] and decision['outcome'] in ('left','right'):
                        winner,loser = (decision['a'], decision['b']) if decision['outcome'] == 'left' else (decision['b'], decision['a'])
                        if positions[winner] > positions[loser]:
                            decision['active'] = False
                            decision['superseded_by'] = 'manual move'
                s.setdefault('moves', []).append(dict(key=k, reason='Manual move', at=now()))
                if c in s['sessions'] and s['sessions'][c]['status'] == 'active':
                    s['sessions'][c]['proposal'] = self.ordered(s['order'][c], s['comparisons'], c)
                return 'Moved a place manually'
            for field in ('attention', 'reference', 'excluded'):
                if field in r:
                    p[field] = bool(r[field])
            if 'reason' in r:
                p['reason'] = str(r['reason'])[:2000]
            if 'band' in r:
                band = r['band']
                if band is not None and band not in s['bands'][c]:
                    raise ValueError('Unknown quality band.')
                p['band'] = band
                # Assigned bands form broad groups; preserve within-band ordering.
                prior = s['order'][c][:]
                bands = s['bands'][c]
                s['order'][c].sort(key=lambda member: bands.index(s['places'][member]['band']) if s['places'][member]['band'] in bands else len(bands))
                if prior != s['order'][c]:
                    s.setdefault('moves', []).append(dict(key=k, reason='Quality band assignment', at=now()))
                if c in s['sessions'] and s['sessions'][c]['status'] == 'active':
                    s['sessions'][c]['proposal'] = self.ordered(s['order'][c], s['comparisons'], c)
            if 'status' in r:
                if r['status'] not in ('reviewed', 'unreviewed', 'uncertain'):
                    raise ValueError('Invalid review status.')
                p['status'] = r['status']
            # Exclusion retains the full order, so restoration uses surviving neighbors.
            session = s['sessions'].get(c)
            if session and session.get('pair') and k in session['pair'] and p['excluded']:
                session['pair'] = self.next_pair(s, c, session)
                if session['pair'] is None:
                    session['notice'] = 'This place was set aside. Review or discard the answers already saved.'
            return 'Updated place review details'
        if action == 'revisit':
            record = next((item for item in s['comparisons'] if item['id'] == r['id'] and item['category'] == c), None)
            if not record:
                raise ValueError('Comparison not found.')
            old_session = s['sessions'].get(c)
            if old_session and old_session['status'] == 'active':
                raise ValueError('Finish or discard this session before revisiting an earlier comparison.')
            if any(s['places'][k]['excluded'] or s['places'][k]['missing'] for k in (record['a'],record['b'])):
                raise ValueError('Restore these places before comparing them again.')
            self.apply(db, s, 'start', dict(category=c, target=record['a'], limit=5))
            s['sessions'][c]['pair'] = [record['a'],record['b']]
            # Keep the old answer active until the new one is confirmed, so conflicts
            # are surfaced instead of silently losing earlier evidence.
            return 'Reopened an earlier comparison'
        if action == 'start':
            existing = s['sessions'].get(c)
            if existing and existing['status'] == 'active':
                raise ValueError('Finish or discard the current session before starting another.')
            limit = int(r.get('limit', 5))
            if limit < 1 or limit > 20:
                raise ValueError('Choose between 1 and 20 comparisons.')
            target = r.get('target')
            if target and target not in s['order'][c]:
                raise ValueError('Choose a place in this category.')
            session = dict(id=str(uuid.uuid4()), status='active', count=0, limit=limit, before=s['order'][c][:],
                           proposal=s['order'][c][:], answers=[], pair=None, target=target, mode='focused' if target else 'mixed', notice='', started=now(), superseded=[], band_suggestions=[])
            s['sessions'][c] = session
            session['pair'] = self.next_pair(s, c, session)
            return 'Started comparison session'
        if action == 'answer':
            session = s['sessions'].get(c)
            if not session or session['status'] != 'active' or not session.get('pair'):
                raise ValueError('There is no active comparison.')
            a,b = session['pair']
            outcome = r['outcome']
            if outcome not in ('left', 'right', 'equal', 'unknown', 'skip'):
                raise ValueError('Unknown comparison answer.')
            record = dict(id=str(uuid.uuid4()), a=a, b=b, outcome=outcome, session=session['id'], at=now(), active=True, category=c)
            # A revised equality must not leave an old strict answer in force.
            for old in s['comparisons']:
                same_pair = {old['a'],old['b']} == {a,b}
                replaces = outcome == 'equal' or (outcome in ('left','right') and old['outcome'] == 'equal')
                if old['active'] and same_pair and replaces:
                    old['active'] = False
                    session.setdefault('superseded', []).append(old['id'])
                    old['superseded_by'] = record['id']
            # Only explicit preferences constrain the ordering.
            comparisons = s['comparisons'] + [record]
            try:
                seed = session['proposal'][:]
                if (outcome == 'left' and seed.index(a) > seed.index(b)) or (outcome == 'right' and seed.index(a) < seed.index(b)):
                    seed.remove(a)
                    seed.insert(seed.index(b) + (outcome == 'right'), a)
                proposed = self.ordered(seed, comparisons, c)
            except Conflict:
                if not r.get('supersede'):
                    raise Conflict('This preference conflicts with earlier comparisons. You can keep the earlier decisions or replace conflicting preferences involving these two places.')
                for old in s['comparisons']:
                    if old['category'] == c and (old['a'] in (a,b) or old['b'] in (a,b)) and old['outcome'] in ('left','right') and old['active']:
                        old['active'] = False
                        session.setdefault('superseded', []).append(old['id'])
                        old['superseded_by'] = record['id']
                proposed = self.ordered(seed, s['comparisons']+[record], c)
            s['comparisons'].append(record)
            session['answers'].append(record['id'])
            session['count'] += 1
            session['proposal'] = proposed
            band_a, band_b = s['places'][a]['band'], s['places'][b]['band']
            bands = s['bands'][c]
            if band_a in bands and band_b in bands:
                contradicts = (outcome == 'left' and bands.index(band_a) > bands.index(band_b)) or (outcome == 'right' and bands.index(band_a) < bands.index(band_b))
                if contradicts:
                    session.setdefault('band_suggestions', []).append(dict(key=a, band=band_b, comparison=record['id']))
            if outcome == 'unknown':
                s['places'][a]['status'] = 'uncertain'
                session['notice'] = 'Set aside for later because you don’t remember this place.'
            session['pair'] = self.next_pair(s, c, session) if session['count'] < session['limit'] and (outcome != 'unknown' or session.get('mode','mixed') == 'mixed') else None
            return 'Saved comparison'
        if action in ('accept', 'discard'):
            session = s['sessions'].get(c)
            if not session or session['status'] != 'active':
                raise ValueError('No active session to finish.')
            if action == 'accept':
                previous = s['order'][c][:]
                s['order'][c] = session['proposal'][:]
                involved = {r['a'] for r in s['comparisons'] if r['session'] == session['id'] and r['outcome'] in ('left','right')}
                for k in involved:
                    if previous.index(k) != s['order'][c].index(k):
                        s.setdefault('moves', []).append(dict(key=k, reason='Accepted comparison', at=now()))
                for record in s['comparisons']:
                    if record['session'] == session['id'] and record['active'] and record['outcome'] in ('left', 'right', 'equal'):
                        k = record['a']
                        if s['places'][k]['status'] != 'uncertain':
                            s['places'][k]['status'] = 'provisional'
            else:
                for record in s['comparisons']:
                    if record['session'] == session['id']:
                        record['active'] = False
                    elif record['id'] in session.get('superseded', []):
                        record['active'] = True
                        record.pop('superseded_by', None)
            session['status'] = 'accepted' if action == 'accept' else 'discarded'
            session['pair'] = None
            return 'Accepted session order' if action == 'accept' else 'Discarded session proposal'
        raise ValueError('Unknown action.')

    @staticmethod
    def ordered(order, comparisons, category):
        graph = {k: set() for k in order}
        incoming = dict.fromkeys(order, 0)
        for r in comparisons:
            if not r['active'] or r['category'] != category or r['outcome'] not in ('left', 'right'):
                continue
            a,b = (r['a'], r['b']) if r['outcome'] == 'left' else (r['b'], r['a'])
            if a in graph and b in graph and b not in graph[a]:
                graph[a].add(b); incoming[b] += 1
        positions = {k:i for i,k in enumerate(order)}
        heap = [(positions[k], k) for k in order if not incoming[k]]
        heapq.heapify(heap)
        result = []
        while heap:
            _,k = heapq.heappop(heap); result.append(k)
            for nxt in graph[k]:
                incoming[nxt] -= 1
                if incoming[nxt] == 0:
                    heapq.heappush(heap, (positions[nxt], nxt))
        if len(result) != len(order):
            raise Conflict('Conflicting preferences form a cycle.')
        return result

    @staticmethod
    def next_pair(s, c, session):
        order = [k for k in session['proposal'] if not s['places'][k]['excluded'] and not s['places'][k]['missing']
                 and (s['places'][k]['status'] != 'uncertain' or (session.get('mode') == 'focused' and session.get('target') == k))]
        if len(order) < 2:
            session['notice'] = 'Fewer than two eligible places remain to compare.'
            return None
        decisions = [r for r in s['comparisons'] if r['active'] and r['category'] == c]
        # Settled, equal, and skipped pairs are not automatically asked again.
        # Explicit Revisit can still reopen any old pair.
        seen = {frozenset((r['a'],r['b'])) for r in decisions}
        positions = {k:i for i,k in enumerate(order)}
        recent = decisions[-20:]
        exposure = {k:sum(k in (r['a'],r['b']) for r in recent) for k in order}
        session_decisions = [r for r in decisions if r['session'] == session['id']]
        session_exposure = {k:sum(k in (r['a'],r['b']) for r in session_decisions) for k in order}
        asked_targets = {r['a'] for r in session_decisions}
        mixed = session.get('mode','mixed') == 'mixed'
        if mixed or not session.get('target'):
            targets = [k for k in order if (s['places'][k]['status'] in ('new','unreviewed') or s['places'][k]['attention'])
                       and (not mixed or (k not in asked_targets and session_exposure[k] < 2))]
            targets.sort(key=lambda k:(s['places'][k]['status'] != 'new', exposure[k], not s['places'][k]['attention'], positions[k]))
            if not targets:
                session['notice'] = 'No more unreviewed places are eligible for this session. Your saved answers are ready to review.'
                return None
        else:
            targets = [session['target']]
        for a in targets:
            if a not in order:
                continue
            session['target'] = a
            graph = {k:set() for k in order}
            reverse = {k:set() for k in order}
            for r in decisions:
                if r['outcome'] not in ('left','right'):
                    continue
                winner,loser = (r['a'],r['b']) if r['outcome']=='left' else (r['b'],r['a'])
                if winner in graph and loser in graph:
                    graph[winner].add(loser); reverse[loser].add(winner)
            def reachable(edges):
                found=set(); todo=list(edges[a])
                while todo:
                    k=todo.pop()
                    if k not in found:
                        found.add(k); todo.extend(edges[k]-found)
                return found
            better,worse=reachable(reverse),reachable(graph)
            candidates=[b for b in order if b != a and b not in better|worse and frozenset((a,b)) not in seen
                        and (not mixed or session_exposure[b] < 2)]
            if not candidates:
                continue
            # Reference order is an explicit user choice. Narrow within those anchors;
            # unreviewed imported positions only suggest questions, never inferred votes.
            references=[b for b in candidates if s['places'][b]['reference']]
            if references:
                low=max((positions[k] for k in better if s['places'][k]['reference']),default=-1)
                high=min((positions[k] for k in worse if s['places'][k]['reference']),default=len(order))
                interval=[b for b in references if low < positions[b] < high]
                if interval:
                    same_band=[b for b in interval if s['places'][b]['band']==s['places'][a]['band']]
                    pool=same_band or interval
                    midpoint=positions[pool[len(pool)//2]]
                    pool.sort(key=lambda k:(exposure[k], abs(positions[k]-midpoint)))
                    session['prompt_reason'] = 'Compare with a reference place you selected.'
                    return [a,pool[0]]
            candidates.sort(key=lambda b:(s['places'][b]['band'] != s['places'][a]['band'],
                                         exposure[b] if mixed else 0,
                                         s['places'][b]['status'] != 'reviewed', abs(positions[b]-positions[a])))
            # Stop once both immediate retained neighbors have supporting evidence.
            idx=positions[a]
            upper=order[idx-1] if idx else None
            lower=order[idx+1] if idx+1 < len(order) else None
            if not mixed and session['count'] and (upper is None or upper in better) and (lower is None or lower in worse):
                session['notice'] = 'This place has supporting comparisons on both sides. Its focused review is complete.'
                return None
            session['prompt_reason'] = ('A fresh pair in this quality band; recent opponents are deprioritized.' if s['places'][a]['band'] else 'No band assigned yet; checking an unreviewed place while avoiding recent opponents.') if mixed else 'Checking this place against nearby placements.'
            return [a,candidates[0]]

        session['notice'] = 'No more eligible, unanswered comparisons are available for this session. You can accept these answers or review a specific place.'
        return None

    def backup(self, destination):
        with self.connect() as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
        Path(destination).chmod(0o600)

    @staticmethod
    def validate_backup(path):
        with closing(sqlite3.connect(path)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup database failed its integrity check.')
            if db.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise ValueError('Unsupported backup version.')
            row = db.execute('SELECT data FROM workspace WHERE id=1').fetchone()
            if not row or not isinstance(json.loads(row[0]).get('order'), dict):
                raise ValueError('Not a Beli Review backup.')
            required = {'workspace','imports','operations','checkpoints','undo_stack'}
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables != required or db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone():
                raise ValueError('Unsupported backup schema.')
            state = json.loads(row[0])
            for source in state['sources']:
                if not db.execute('SELECT 1 FROM imports WHERE id=?',(source,)).fetchone():
                    raise ValueError('Backup is missing an imported source.')
