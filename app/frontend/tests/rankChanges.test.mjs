import assert from 'node:assert/strict';
import test from 'node:test';
import { rankChanges } from '../src/rankChanges.ts';

test('deleting a middle place does not mark surviving places moved', () => {
  assert.deepEqual(rankChanges(['a', 'b', 'c', 'd'], ['a', 'c', 'd']).moved, []);
});
test('inserting a place shows only the new place', () => {
  assert.deepEqual(rankChanges(['a', 'b', 'c'], ['a', 'new', 'b', 'c']).moved, ['new']);
});
test('true swaps are shown, with the actual ranks retained', () => {
  const result = rankChanges(['a', 'b', 'c', 'd'], ['a', 'd', 'c']);
  assert.deepEqual(result.moved, ['d', 'c']);
  assert.equal(result.beforeRanks.get('d'), 3);
  assert.equal(result.keptRanks.get('d'), 1);
});
test('empty and entirely replaced lists', () => {
  assert.deepEqual(rankChanges([], []).moved, []);
  assert.deepEqual(rankChanges(['a'], []).moved, []);
  assert.deepEqual(rankChanges(['a'], ['b']).moved, ['b']);
});
