/* Runs that have ended, furthest first. */

import { call, refresh, register } from '../app.js';
import { notice, section, stats, table } from '../components/index.js';

const COLUMNS = [
  { key: 'reached', label: 'Reached' },
  { key: 'army', label: 'Army' },
  { key: 'outcome', label: 'Outcome' },
  { key: 'battles', label: 'Battles' },
  { key: 'kills', label: 'Kills' },
  { key: 'score', label: 'Score' },
  { key: 'ore', label: 'Ore earned' },
  { key: 'ended', label: 'Ended' },
];

/* Which run is being looked at, by its own id rather than by where it sat
 * in the list. The board is kept furthest first, so one run ending moves
 * every row below it -- and a remembered position would then be pointing
 * at somebody else's run. */
let selected = null;

async function render(root) {
  const entries = await call('skirmish.board');
  if (!entries.length) {
    root.replaceChildren(notice('No run has ended yet.'));
    return;
  }
  const rows = entries.map((entry) => {
    const row = { run_id: entry.run_id };
    COLUMNS.forEach((column, index) => {
      row[column.key] = entry.row[index];
    });
    return row;
  });
  const at = rows.findIndex((row) => row.run_id === selected);
  const chosen = at < 0 ? null : entries[at];
  root.replaceChildren(
    section('Records', table(COLUMNS, rows, {
      selected: at < 0 ? null : at,
      onSelect: (row) => {
        selected = row.run_id;
        refresh();
      },
    })),
    chosen
      ? section(`${chosen.reached} — seed ${chosen.seed}`,
        stats(chosen.stat_lines))
      : section(null, notice('Select a run to see what it did.')),
  );
}

register('records', render);
