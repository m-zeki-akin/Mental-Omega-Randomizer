/* The board a Grid run is played on.
 *
 * Grid is the one mode whose order is not a list. What is open is decided
 * by what a finished mission sits next to, so the mission table beside
 * this describes it about as well as a list of streets describes a town:
 * everything true, nothing shaped.
 *
 * The board is small -- a dozen tiles at most -- so it is drawn whole,
 * where it is, and a tile is where the mission is fought from. */

import { act, call, refresh, register, status } from '../app.js';
import { el, notice, panel, section, stats } from '../components/index.js';

/* Redrawn on the same beat as the Run screen while a mission is up: the
 * tiles a win opens are the point of the board, and they should appear
 * without anybody pressing anything. */
const POLL_MS = 2000;
let polling = null;

function watch() {
  if (polling) return;
  polling = setInterval(async () => {
    let session;
    try {
      session = await call('campaign.session');
    } catch {
      return;
    }
    if (session.playing) {
      await refresh();
      return;
    }
    clearInterval(polling);
    polling = null;
    await refresh();
    if (session.finished) status(session.finished.message || '');
  }, POLL_MS);
}

function tile(one, busy) {
  const open = one.installed && one.unlocked && !busy;
  const parts = [
    el('div', { class: 'tile__name', text: one.name }),
    el('div', {
      class: 'tile__note',
      text: one.total ? `${one.done} / ${one.total}` : 'not installed',
    }),
  ];
  if (one.finish) parts.push(el('span', { class: 'pill', text: 'the last one' }));
  if (open) {
    parts.push(el('button', {
      class: one.complete ? 'button' : 'button button--primary',
      type: 'button',
      text: one.complete ? 'Play again' : 'Fight',
      onClick: async () => {
        status(`Preparing ${one.name}…`);
        const started = await act('campaign.launch', { code: one.code });
        if (started) status(`${started.name} is starting.`);
      },
    }));
  }
  return el('div', {
    class: `tile tile--${one.standing}${one.finish ? ' tile--finish' : ''}`,
    title: `${one.code} — ${one.side || 'Unknown side'}`,
  }, parts);
}

function header(board, playing) {
  return panel('This board', {
    children: [stats([
      `Seed ${board.seed}`,
      `${board.width} by ${board.height}`,
      `${board.won} of ${board.tiles.length} finished`,
      board.finish ? `Ends at ${board.finish}` : '',
      playing ? `${playing} is being played` : '',
    ].filter(Boolean))],
  });
}

async function render(root) {
  const answer = await call('campaign.board');
  const board = answer.board;
  if (!board) {
    root.replaceChildren(section('Board', notice(
      'The run standing was not dealt as a board. Grid deals one when it '
      + 'generates a run; the Run tab shows what this one is.',
    )));
    return;
  }
  const session = await call('campaign.session');
  if (session.playing) watch();
  const grid = el('div', { class: 'board' },
    board.tiles.map((one) => tile(one, Boolean(session.playing))));
  grid.style.gridTemplateColumns = `repeat(${board.width || 1}, minmax(0, 1fr))`;
  root.replaceChildren(
    section(null, header(board, session.playing ? session.code : '')),
    section('Board', grid),
  );
}

register('board', render);
