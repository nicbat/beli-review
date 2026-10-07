/** Compare surviving places by relative order, while displaying actual ranks.
 * Removing or inserting a place alone must not mark every later place moved.
 */
export function rankChanges(before: string[], kept: string[]) {
  const beforeRanks = new Map(before.map((key, index) => [key, index]));
  const keptRanks = new Map(kept.map((key, index) => [key, index]));
  const beforeCommon = before.filter((key) => keptRanks.has(key));
  const commonRanks = new Map(beforeCommon.map((key, index) => [key, index]));
  let commonIndex = 0;
  const moved = kept.filter((key) => {
    if (!beforeRanks.has(key)) return true;
    return commonRanks.get(key) !== commonIndex++;
  });
  return { beforeRanks, keptRanks, moved };
}
