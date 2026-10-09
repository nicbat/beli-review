import unittest
from app.backend.verification import analyze, confirmation
from app.backend.store import Store


def workspace():
    keys = [f'RES:{i}' for i in range(1, 7)]
    return dict(order={'RES': keys}, places={k: dict(band='Good', status='provisional', excluded=False, missing=False, attention=False, reference=False) for k in keys},
                bands={'RES': ['Great', 'Good', 'Fine']}, comparisons=[])


def vote(s, a, b, outcome='left'):
    s['comparisons'].append(dict(id=str(len(s['comparisons'])), a=f'RES:{a}', b=f'RES:{b}',
                                outcome=outcome, active=True, category='RES', session='old'))


class VerificationTests(unittest.TestCase):
    def test_transitive_support_and_band_conflict_explain_chain(self):
        s = workspace()
        vote(s, 1, 2); vote(s, 2, 3)
        s['places']['RES:1']['band'] = 'Fine'
        s['places']['RES:3']['band'] = 'Great'
        report = analyze(s, 'RES')
        issues = report['places']['RES:1']['issues']
        self.assertTrue(any(i['chain'] == ['RES:1', 'RES:2', 'RES:3'] and i['comparisons'] == ['0', '1'] for i in issues))
        self.assertEqual(report['places']['RES:3']['status'], 'conflict')

    def test_distinguishes_insufficient_unchecked_supported(self):
        s = workspace()
        vote(s, 1, 2)
        report = analyze(s, 'RES')
        self.assertEqual(report['places']['RES:1']['status'], 'supported')
        self.assertEqual(report['places']['RES:2']['status'], 'unchecked')
        self.assertEqual(report['places']['RES:3']['status'], 'insufficient')
        self.assertEqual(report['counts']['needs_verification'], 1)

    def test_confirmation_tracks_relative_changes_not_deletion(self):
        s = workspace()
        k = 'RES:3'
        s['places'][k]['status'] = 'reviewed'
        s['places'][k]['confirmation'] = confirmation(s, 'RES', k)
        s['places']['RES:1']['excluded'] = True
        self.assertEqual(analyze(s, 'RES')['places'][k]['status'], 'confirmed')
        s['order']['RES'].remove(k)
        s['order']['RES'].append(k)
        self.assertEqual(analyze(s, 'RES')['places'][k]['status'], 'changed')
        s['places'][k]['confirmation'] = confirmation(s, 'RES', k)
        self.assertEqual(analyze(s, 'RES')['places'][k]['status'], 'confirmed')

    def test_confirmed_does_not_hide_conflict_and_ignored_votes_dont_count(self):
        s = workspace()
        vote(s, 2, 1)
        s['places']['RES:1']['status'] = 'reviewed'
        self.assertEqual(analyze(s, 'RES')['places']['RES:1']['status'], 'conflict')
        s['comparisons'][0]['active'] = False
        vote(s, 3, 4, 'skip')
        self.assertEqual(analyze(s, 'RES')['counts']['compared'], 0)

    def test_verification_continues_after_all_places_provisional(self):
        s = workspace()
        vote(s, 1, 2)
        session = dict(id='new', mode='verify', proposal=s['order']['RES'][:], count=0)
        pair = Store.next_pair(s, 'RES', session)
        self.assertEqual(pair, ['RES:2', 'RES:3'])
        self.assertIn('Verification', session['prompt_reason'])

    def test_verification_does_not_repeat_or_ask_inferred_pairs(self):
        s = workspace()
        for a in range(1, 6):
            vote(s, a, a+1)
        session = dict(id='new', mode='verify', proposal=s['order']['RES'][:], count=0)
        self.assertIsNone(Store.next_pair(s, 'RES', session))
        self.assertEqual(analyze(s, 'RES')['counts']['supported'], 6)

    def test_equal_neighbors_support_placement(self):
        s = workspace()
        vote(s, 1, 2, 'equal')
        self.assertEqual(analyze(s, 'RES')['places']['RES:1']['status'], 'supported')

    def test_missing_and_excluded_not_counted(self):
        s = workspace()
        vote(s, 2, 1)
        s['places']['RES:1']['missing'] = True
        s['places']['RES:3']['excluded'] = True
        report = analyze(s, 'RES')
        self.assertEqual(report['counts']['total'], 4)
        self.assertEqual(report['counts']['conflict'], 0)
