from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from app.backend.store import Store, Conflict, normalize


def fixture(ids=(1,2,3,4,5,6), stamp='2026-10-06T10:00:00+00:00', category='RES'):
    return dict(exported_at=stamp, rankings_by_category={category:[dict(id=i+100,user='account-a',business=dict(id=i,name=f'Place {i}',city='Test City',cuisines=['Test']),score=10-i/10,value=3-i/10,visit_dates=[]) for i in ids]},
                notes=[dict(id=900,user='account-a',business=1,value='A memorable visit')],
                photos=[dict(id=800,user='account-a',business=1,image='https://photos2.beliapp.cloud/example.jpg',description='A caption')])


class WorkshopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'workspace.sqlite3'
        self.store=Store(self.path)
        self.action('import',payload=fixture())

    def tearDown(self):
        self.temp.cleanup()

    def action(self,action,**kwargs):
        return self.store.mutate(dict(action=action,revision=self.store.view()['revision'],operation_id=str(uuid.uuid4()),category='RES',**kwargs))

    def state(self):
        return self.store.view()['state']

    def test_import_and_restart(self):
        self.action('place',key='RES:1',attention=True,reason='Remember this')
        self.assertEqual(Store(self.path).view()['state']['places']['RES:1']['reason'],'Remember this')
        self.assertEqual(len(self.store.view()['entries']),6)
        self.assertFalse(self.store.view()['entries']['RES:1']['flags']['no_note'])
        self.assertTrue(self.store.view()['entries']['RES:2']['flags']['no_photos'])

    def test_same_import_preview_is_noop(self):
        self.assertTrue(self.store.preview(fixture())['duplicate'])
        rev=self.store.view()['revision']
        with self.assertRaises(ValueError):
            self.action('import',payload=fixture())
        self.assertEqual(self.store.view()['revision'],rev)

    def test_account_and_duplicate_validation(self):
        bad=fixture();bad['rankings_by_category']['RES'][0]['user']='other'
        with self.assertRaises(ValueError):normalize(bad)
        bad=fixture((1,1))
        with self.assertRaises(ValueError):normalize(bad)
        bad=fixture();bad['photos'][0]['user']='other'
        with self.assertRaises(ValueError):normalize(bad)

    def test_revision_and_retry_deduplication(self):
        request=dict(action='place',key='RES:1',attention=True,category='RES',revision=self.store.view()['revision'],operation_id='repeatable')
        self.store.mutate(request)
        self.assertTrue(self.store.mutate(request)['duplicate'])
        request['operation_id']='new'
        with self.assertRaises(Conflict):self.store.mutate(request)

    def test_missing_records_are_retained(self):
        self.action('place',key='RES:2',excluded=True,reason='No longer want this')
        self.action('import',payload=fixture((1,3,4,5,6,7),'2026-10-07T10:00:00+00:00'))
        s=self.state()
        self.assertTrue(s['places']['RES:2']['missing'])
        self.assertTrue(s['places']['RES:2']['excluded'])
        self.assertIn('RES:2',self.store.view()['entries'])
        self.assertEqual(s['places']['RES:7']['status'],'new')

    def test_changed_beli_order_does_not_overwrite_local(self):
        self.action('move',key='RES:1',anchor='RES:6',side='after')
        before=self.state()['order']['RES'][:]
        self.action('import',payload=fixture((6,5,4,3,2,1),'2026-10-07T10:00:00+00:00'))
        self.assertEqual(self.state()['order']['RES'],before)
        self.assertEqual(self.store.view()['latest']['RES'][0],'RES:6')
        self.assertEqual(self.store.view()['original']['RES'][0],'RES:1')

    def test_source_content_refresh_keeps_history(self):
        source=fixture(stamp='2026-10-07T10:00:00+00:00')
        source['notes'][0]['value']='Updated note'
        self.action('import',payload=source)
        self.assertEqual(self.store.view()['entries']['RES:1']['notes'][0]['value'],'Updated note')
        with self.store.connect() as db:
            original=self.store.source(db,self.state()['original'])
            self.assertEqual(original['entries']['RES:1']['notes'][0]['value'],'A memorable visit')

    def test_older_export_only_archived(self):
        before=self.state()
        self.action('import',payload=fixture((9,10),'2026-10-01T10:00:00+00:00'))
        self.assertEqual(self.state(),before)
        self.assertEqual(len(self.store.view()['imports']),2)

    def test_category_transfer(self):
        export=fixture((1,2,3),'2026-10-07T10:00:00+00:00','COF')
        preview=self.store.preview(export)
        self.assertEqual(len(preview['transfers']),3)
        self.action('import',payload=export)
        self.assertTrue(self.state()['places']['RES:1']['missing'])
        self.assertEqual(self.state()['places']['COF:1']['status'],'new')

    def test_session_resume_and_skip(self):
        self.action('start')
        first=self.state()['sessions']['RES']['pair']
        self.assertIsNotNone(first)
        self.action('answer',outcome='skip')
        session=self.state()['sessions']['RES']
        self.assertNotEqual(set(first),set(session['pair']))
        self.assertEqual(Store(self.path).view()['state']['sessions']['RES'],session)
        self.assertEqual(self.state()['order']['RES'],session['before'])

    def test_equal_unknown_do_not_reorder(self):
        self.action('start')
        before=self.state()['order']['RES'][:]
        self.action('answer',outcome='equal')
        self.action('answer',outcome='unknown')
        self.action('accept')
        self.assertEqual(self.state()['order']['RES'],before)

    def test_excluded_places_not_scheduled_and_restorable(self):
        self.action('place',key='RES:1',excluded=True)
        self.action('start')
        self.assertNotIn('RES:1',self.state()['sessions']['RES']['pair'])
        self.action('place',key='RES:1',excluded=False)
        self.assertEqual(self.state()['order']['RES'][0],'RES:1')

    def test_import_mid_session_keeps_new_member_after_accept(self):
        self.action('start');self.action('answer',outcome='right')
        session_id=self.state()['sessions']['RES']['id']
        self.action('import',payload=fixture((1,2,3,4,5,6,7),'2026-10-07T10:00:00+00:00'))
        self.assertEqual(self.state()['sessions']['RES']['id'],session_id)
        self.action('accept')
        self.assertIn('RES:7',self.state()['order']['RES'])
        self.assertEqual(len(self.state()['order']['RES']),7)

    def test_bands_group_preserving_order(self):
        self.action('place',key='RES:5',band='Favorites')
        self.action('place',key='RES:6',band='Favorites')
        self.assertEqual(self.state()['order']['RES'][:2],['RES:5','RES:6'])
        self.action('bands',bands=['Wonderful','Very good','Good','Disappointing'])
        self.assertEqual(self.state()['places']['RES:5']['band'],'Wonderful')

    def test_undo_redo_across_restart(self):
        self.action('place',key='RES:1',attention=True)
        self.action('undo')
        self.assertFalse(self.state()['places']['RES:1']['attention'])
        self.store=Store(self.path)
        self.action('redo')
        self.assertTrue(self.state()['places']['RES:1']['attention'])
        self.action('undo');self.action('place',key='RES:2',attention=True)
        self.assertFalse(self.store.view()['can_redo'])

    def test_checkpoints_restore_and_import_undo(self):
        self.action('checkpoint',name='Before change')
        cp=self.store.view()['checkpoints'][0]['id']
        self.action('place',key='RES:1',attention=True)
        self.action('restore',id=cp)
        self.assertFalse(self.state()['places']['RES:1']['attention'])
        self.action('import',payload=fixture((1,2,3,7),'2026-10-07T10:00:00+00:00'))
        self.action('undo')
        self.assertNotIn('RES:7',self.state()['places'])
        self.action('redo')
        self.assertIn('RES:7',self.state()['places'])

    def test_cycle_detection(self):
        order=['a','b','c']
        comparisons=[dict(a='a',b='b',outcome='left',active=True,category='RES'),dict(a='b',b='c',outcome='left',active=True,category='RES'),dict(a='c',b='a',outcome='left',active=True,category='RES')]
        with self.assertRaises(Conflict):Store.ordered(order,comparisons,'RES')
        comparisons[-1]['active']=False
        self.assertEqual(Store.ordered(order,comparisons,'RES'),order)

    def test_failure_does_not_increment_revision(self):
        before=self.store.view()
        with self.assertRaises(ValueError):self.action('place',key='RES:1',band='Does not exist')
        self.assertEqual(self.store.view()['revision'],before['revision'])
        self.assertEqual(self.state(),before['state'])

    def test_backup_restores_full_workspace(self):
        self.action('start');self.action('answer',outcome='right')
        backup=Path(self.temp.name)/'backup.sqlite3'
        self.store.backup(backup);Store.validate_backup(backup)
        restored=Store(backup).view()
        self.assertEqual(restored,self.store.view())
        with closing(sqlite3.connect(backup)) as db:db.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError):Store.validate_backup(backup)

    def test_supported_preference_does_not_move_target(self):
        self.action('place',key='RES:6',reference=True)
        self.action('start',target='RES:1')
        self.assertEqual(self.state()['sessions']['RES']['pair'],['RES:1','RES:6'])
        self.action('answer',outcome='left')
        self.assertEqual(self.state()['sessions']['RES']['proposal'],self.state()['order']['RES'])

    def test_unknown_stops_questioning_same_place(self):
        self.action('start',target='RES:1')
        self.action('answer',outcome='unknown')
        self.assertIsNone(self.state()['sessions']['RES']['pair'])
        self.action('accept')
        self.action('start')
        self.assertNotEqual(self.state()['sessions']['RES']['target'],'RES:1')

    def test_accepted_target_not_repeated_in_next_session(self):
        self.action('start')
        self.action('answer',outcome='left')
        self.action('accept')
        self.action('start')
        self.assertNotIn(self.state()['sessions']['RES']['target'],['RES:1','RES:2'])

    def test_revisit_conflict_discard_restores_old_evidence(self):
        self.action('start')
        self.action('answer',outcome='left')
        self.action('accept')
        old=self.state()['comparisons'][0]['id']
        self.action('revisit',id=old)
        with self.assertRaises(Conflict):self.action('answer',outcome='right')
        self.action('answer',outcome='right',supersede=True)
        self.assertFalse(self.state()['comparisons'][0]['active'])
        self.action('discard')
        self.assertTrue(self.state()['comparisons'][0]['active'])
        self.assertFalse(self.state()['comparisons'][-1]['active'])

    def test_band_boundary_suggests_reclassification(self):
        self.action('place',key='RES:1',band='Favorites')
        self.action('place',key='RES:2',band='Good')
        self.action('start',target='RES:1')
        self.action('answer',outcome='right')
        self.assertEqual(self.state()['sessions']['RES']['band_suggestions'][0]['band'],'Good')

    def test_missing_attachments_retained_as_historical(self):
        export=fixture(stamp='2026-10-07T10:00:00+00:00')
        export['notes']=[];export['photos']=[]
        self.action('import',payload=export)
        e=self.store.view()['entries']['RES:1']
        self.assertTrue(e['flags']['no_note'])
        self.assertEqual(len(e['previous_notes']),1)
        self.assertEqual(len(e['previous_photos']),1)

    def test_revised_equality_replaces_prior_strict_answer(self):
        self.action('start');self.action('answer',outcome='left');self.action('accept')
        self.action('revisit',id=self.state()['comparisons'][0]['id'])
        self.action('answer',outcome='equal')
        self.assertFalse(self.state()['comparisons'][0]['active'])
        self.action('discard')
        self.assertTrue(self.state()['comparisons'][0]['active'])

    def test_mixed_session_spreads_questions_across_places(self):
        self.action('start')
        for _ in range(5):
            if not self.state()['sessions']['RES']['pair']:
                break
            self.action('answer',outcome='equal')
        decisions=self.state()['comparisons']
        self.assertGreaterEqual(len(decisions),3)
        targets=[r['a'] for r in decisions]
        self.assertEqual(len(targets),len(set(targets)))
        for k in self.state()['order']['RES']:
            self.assertLessEqual(sum(k in (r['a'],r['b']) for r in decisions),2)

    def test_mixed_unknown_moves_on_to_fresh_place(self):
        self.action('start');self.action('answer',outcome='unknown')
        pair=self.state()['sessions']['RES']['pair']
        self.assertIsNotNone(pair)
        self.assertNotIn('RES:1',pair)

    def test_focused_review_keeps_requested_target(self):
        self.action('start',target='RES:1');self.action('answer',outcome='equal')
        self.assertEqual(self.state()['sessions']['RES']['pair'][0],'RES:1')

    def test_skipped_pair_not_automatically_repeated(self):
        self.action('start',target='RES:1')
        pair=self.state()['sessions']['RES']['pair']
        self.action('answer',outcome='skip');self.action('accept')
        self.action('start',target='RES:1')
        self.assertNotEqual(set(self.state()['sessions']['RES']['pair']),set(pair))

if __name__=='__main__':unittest.main()
