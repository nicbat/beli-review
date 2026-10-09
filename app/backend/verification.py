"""Derived verification evidence. Never changes saved judgments."""
from collections import deque


def confirmation(state, category, key):
    order = [k for k in state['order'][category]
             if not state['places'][k]['excluded'] and not state['places'][k]['missing']]
    return dict(order=order, band=state['places'][key]['band'])


def analyze(state, category, order=None):
    order = [k for k in (order if order is not None else state['order'].get(category, []))
             if not state['places'][k]['excluded'] and not state['places'][k]['missing']]
    positions = {k: i for i, k in enumerate(order)}
    graph = {k: {} for k in order}
    equal = set()
    records = [r for r in state['comparisons'] if r['active'] and r['category'] == category
               and r['a'] in positions and r['b'] in positions]
    compared = set()
    for r in records:
        a, b = r['a'], r['b']
        if r['outcome'] in ('left', 'right', 'equal'):
            compared.update((a, b))
        if r['outcome'] == 'equal':
            equal.add(frozenset((a, b)))
        if r['outcome'] in ('left', 'right'):
            winner, loser = (a, b) if r['outcome'] == 'left' else (b, a)
            graph[winner][loser] = r['id']
    # Keep predecessor trees so explanations can show the actual evidence chain.
    paths = {}
    for root in order:
        parents, todo = {}, deque([root])
        while todo:
            node = todo.popleft()
            for nxt, record_id in graph[node].items():
                if nxt not in parents and nxt != root:
                    parents[nxt] = (node, record_id)
                    todo.append(nxt)
        paths[root] = parents

    def evidence(a, b):
        chain, ids = [b], []
        while b != a:
            b, rid = paths[a][b]
            chain.append(b)
            ids.append(rid)
        return dict(chain=list(reversed(chain)), comparisons=list(reversed(ids)))

    bands = state['bands'].get(category, [])
    band_index = {name: i for i, name in enumerate(bands)}
    issues = {k: [] for k in order}
    for a in order:
        for b in paths[a]:
            ba, bb = state['places'][a]['band'], state['places'][b]['band']
            band_conflict = ba in band_index and bb in band_index and band_index[ba] > band_index[bb]
            order_conflict = positions[a] > positions[b]
            if band_conflict or order_conflict:
                item = dict(kind='conflict', reason='Preference contradicts quality bands' if band_conflict else 'Preference contradicts current order',
                            **evidence(a, b))
                issues[a].append(item)
                issues[b].append(item)
    counts = dict(total=len(order), labeled=0, compared=len(compared), confirmed=0,
                  conflict=0, changed=0, unchecked=0, insufficient=0, supported=0, uncertain=0, needs_verification=0)
    places = {}
    for k in order:
        p = state['places'][k]
        if p['band'] is not None:
            counts['labeled'] += 1
        snapshot = p.get('confirmation')
        changed = False
        if snapshot:
            old = snapshot['order']
            if k in old:
                above = set(old[:old.index(k)])
                below = set(old[old.index(k)+1:])
                changed = (any(positions[x] > positions[k] for x in above if x in positions)
                           or any(positions[x] < positions[k] for x in below if x in positions)
                           or snapshot['band'] != p['band'])
        if changed:
            issues[k].append(dict(kind='changed', reason='Relative placement or band changed since your confirmation', chain=[], comparisons=[]))
        peers = [x for x in order if state['places'][x]['band'] == p['band']]
        idx = peers.index(k)
        neighbors = ([peers[idx-1]] if idx else []) + ([peers[idx+1]] if idx+1 < len(peers) else [])
        unresolved = []
        for neighbor in neighbors:
            a, b = (neighbor, k) if positions[neighbor] < positions[k] else (k, neighbor)
            if b not in paths[a] and frozenset((a, b)) not in equal:
                unresolved.append(neighbor)
        if any(i['kind'] == 'conflict' for i in issues[k]):
            status = 'conflict'
        elif changed:
            status = 'changed'
        elif p['status'] == 'uncertain':
            status = 'uncertain'
        elif p['status'] == 'reviewed':
            status = 'confirmed'
        elif k not in compared:
            status = 'insufficient'
        elif unresolved or p['band'] is None:
            status = 'unchecked'
        else:
            status = 'supported'
        counts[status] += 1
        if status in ('conflict', 'changed', 'unchecked'):
            counts['needs_verification'] += 1
        places[k] = dict(status=status, issues=issues[k], unresolved=unresolved,
                         neighbors=neighbors, compared=k in compared)
    return dict(counts=counts, places=places)
