/* The Skirmish Shop mode: the run, what it is offered, what it can buy. */

import { act, call, refresh, register, status } from '../app.js';
import {
  button, card, count, el, figure, grid, notice, pill, section, stats,
} from '../components/index.js';

const SKILL_VARIANT = {
  green: 'green',
  trained: 'trained',
  hardened: 'hardened',
};

/** The line under a battle card, as pills rather than a sentence. */
function offerPills(offer) {
  const marks = [];
  for (const enemy of offer.enemies) {
    marks.push(pill(enemy.label, SKILL_VARIANT[enemy.skill] || null));
  }
  if (!offer.ally) marks.push(pill('no ally', 'danger'));
  if (offer.mental_ai) marks.push(pill('boosted AI', 'danger'));
  if (offer.challenge) marks.push(pill('challenge', 'accent'));
  if (offer.bonus_percent) {
    marks.push(pill(`+${offer.bonus_percent}% Ore`, 'ore'));
  }
  return marks;
}

/* One picture per map, fetched once. They run to a hundred kilobytes and
 * they do not change, so asking for them again on every redraw would be
 * the most expensive thing this screen does. */
const previews = new Map();

async function loadPreviews(offers) {
  await Promise.all(offers
    .filter((offer) => offer.has_preview && !previews.has(offer.map_path))
    .map(async (offer) => {
      try {
        const answer = await call('skirmish.preview', {
          map_path: offer.map_path,
        });
        previews.set(offer.map_path, answer.uri || '');
      } catch {
        previews.set(offer.map_path, '');
      }
    }));
}

function offerCard(offer, run) {
  const committed = run.committed_offer;
  const blocked = committed !== null && committed !== offer.index;
  return card({
    title: offer.map_name,
    figure: figure(previews.get(offer.map_path), offer.map_name),
    body: offer.installed
      ? offer.summary
      : 'This map is not installed any more.',
    pills: offerPills(offer),
    state: blocked ? 'taken' : null,
    footer: [
      el('span', { class: 'muted', text: `${offer.seats} seats` }),
      button(offer.challenge ? 'Fight challenge' : 'Fight', {
        variant: 'primary',
        disabled: blocked || !offer.installed || !run.active,
        onClick: async () => {
          // Only watch a battle that started. Watching one that did not
          // would redraw two seconds later and wipe the refusal off the
          // title bar, leaving a button that looks like it did nothing.
          if (await act('skirmish.launch', { index: offer.index })) watch();
        },
      }),
    ],
  });
}

function upgradeCard(upgrade, run) {
  return card({
    title: upgrade.owned ? `Owned — ${upgrade.name}` : upgrade.name,
    body: upgrade.effect,
    title_attr: upgrade.description || upgrade.name,
    state: upgrade.owned ? 'taken' : null,
    footer: [
      el('span', {
        class: upgrade.owned ? 'muted' : 'ore',
        text: upgrade.owned ? 'Bought' : `${count(upgrade.price)} Ore`,
      }),
      button(upgrade.owned ? 'Bought' : 'Buy', {
        disabled: upgrade.owned || !run.active || run.coins < upgrade.price,
        onClick: () => act('skirmish.buy', { key: upgrade.key }),
      }),
    ],
  });
}

function header(run) {
  return el('div', { class: 'row' }, [
    el('strong', { text: run.progress }),
    pill(`${run.player.display}`, 'accent'),
    pill(`ally: ${run.ally.display}`),
    el('span', { class: 'ore', text: `${count(run.coins)} Ore` }),
    el('span', { class: 'titlebar__spacer' }),
    run.warmup && button('Skip warmup', {
      variant: 'quiet',
      onClick: () => act('skirmish.skip_warmup'),
    }),
    button('Give up run', {
      variant: 'danger',
      disabled: !run.active,
      onClick: () => act('skirmish.give_up'),
    }),
  ]);
}

/* While a battle is up there is nothing to decide, so the screen says so
 * and asks again. The first read after the game closes is the one that
 * records the outcome, which is why this keeps asking rather than waiting
 * for the window to be clicked. */
const POLL_MS = 2000;
let polling = null;

function watch() {
  if (polling) return;
  polling = setInterval(async () => {
    let session;
    try {
      session = await call('skirmish.session');
    } catch {
      return;
    }
    if (session.playing) return;
    clearInterval(polling);
    polling = null;
    // Redrawing clears the title bar, so how the battle ended is said
    // after the screen comes back rather than before it.
    await refresh();
    if (session.finished) status(session.finished.message || '');
  }, POLL_MS);
}

function playingNotice(session) {
  return notice(
    `${session.map_name} is being played. This screen comes back when `
    + 'the game closes.',
  );
}

async function render(root) {
  const session = await call('skirmish.session');
  if (session.playing) {
    watch();
    root.replaceChildren(playingNotice(session));
    return;
  }
  let run = await call('skirmish.run');
  if (!run) {
    root.replaceChildren(
      notice('No run yet. Start one on the Setup tab.'),
    );
    return;
  }
  /* A battle that has just been won, skipped or walked into clears the
   * table behind it. Reading is not allowed to deal a new one, so a screen
   * that finds none asks for them and reads again. */
  if (run.active && !run.offers.length) {
    await call('skirmish.deal');
    run = await call('skirmish.run');
  }
  await loadPreviews(run.offers);
  const parts = [section(null, header(run))];
  if (run.offers.length) {
    parts.push(section(
      run.warmup ? 'Warmup' : `Battle ${run.battle}`,
      grid(run.offers.map((offer) => offerCard(offer, run)), { wide: true }),
    ));
  }
  if (run.warmup) {
    parts.push(section('Upgrades', notice(
      'The warmup is fought with what you have. The shop opens once it '
      + 'is behind you.',
    )));
  } else if (run.shelf.length) {
    parts.push(section(
      'Upgrades',
      grid(run.shelf.map((upgrade) => upgradeCard(upgrade, run))),
    ));
  }
  parts.push(section('This run', stats(run.stat_lines)));
  root.replaceChildren(...parts);
}

register('skirmish', render);
