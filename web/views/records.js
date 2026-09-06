/* Runs that have ended, furthest first. */

import { call, register } from '../app.js';
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

let selected = null;

async function render(root) {
  const entries = await call('skirmish.board');
  if (!entries.length) {
    root.replaceChildren(notice('No run has ended yet.'));
    return;
  }
  const rows = entries.map((entry) => {
    const row = {};
    COLUMNS.forEach((column, index) => {
      row[column.key] = entry.row[index];
    });
    return row;
  });
  const chosen = entries[selected] || null;
  root.replaceChildren(
    section('Records', table(COLUMNS, rows, {
      selected,
      onSelect: (_row, index) => {
        selected = index;
        render(root);
      },
    })),
    chosen
      ? section(`${chosen.reached} — seed ${chosen.seed}`,
        stats(chosen.stat_lines))
      : section(null, notice('Select a run to see what it did.')),
  );
}

register('records', render);
