/* The Skirmish Shop mode: the run, what it is offered, what it can buy. */

import { act, call, refresh, register, status } from '../app.js';
import {
  button, card, count, el, figure, grid, notice, pill, row, section,
  stats,
} from '../components/index.js';

const SKILL_VARIANT = {
  green: 'green',
  trained: 'trained',
  hardened: 'hardened',
};

/**
 * What each enemy of this battle carries, army by army, as tooltip text.
 *
 * `lists` is one list of names per enemy, in the order the enemies are
 * named on the card. An army with nothing is still named, so the reader
 * can see which of the three it is.
 */
function byArmy(offer, lists) {
  return (lists || []).map((names, index) => {
    const enemy = offer.enemies[index] || {};
    const who = enemy.display || enemy.label || `Enemy ${index + 1}`;
    return `${who}: ${names.length ? names.join(', ') : 'nothing'}`;
  }).join('\n');
}

/** The line under a battle card, as pills rather than a sentence. */
function offerPills(offer) {
  const marks = [];
  for (const enemy of offer.enemies) {
    marks.push(pill(enemy.label, SKILL_VARIANT[enemy.skill] || null));
  }
  if (!offer.ally) marks.push(pill('no ally', 'danger'));
  if (offer.mental_ai) marks.push(pill('boosted AI', 'danger'));
  if (offer.enemy_upgrades) {
    // The count on the pill, the names under the pointer. A late battle
    // arms three enemies with dozens of rows each, which is a footnote
    // to the decision rather than a panel under the table.
    marks.push(pill(
      offer.enemy_upgrades === 1
        ? 'enemy carries 1 upgrade'
        : `enemy carries ${offer.enemy_upgrades} upgrades`,
      'danger',
      byArmy(offer, offer.enemy_carried),
    ));
  }
  // And what the offer itself bought that army, which is a different
  // thing: named rather than counted, because "enemy army: Firepower,
  // Armour" says what kind of harder this battle is and a number does
  // not.
  if (offer.enemy_army_stats && offer.enemy_army_stats.length) {
    // Across all of them, so a late battle can name seven. The first
    // three and a count reads; the whole list is a paragraph on a pill,
    // so the rest is under the pointer with the army it belongs to.
    const stats = offer.enemy_army_stats;
    const shown = stats.slice(0, 3).join(', ');
    marks.push(pill(
      stats.length > 3
        ? `enemy armies: ${shown} +${stats.length - 3} more`
        : `enemy armies: ${shown}`,
      'danger',
      byArmy(offer, offer.enemy_army_carried),
    ));
  }
  if (offer.modifiers && offer.modifiers.includes('stolen')) {
    marks.push(pill('enemy has infiltrated', 'danger'));
  }
  if (offer.challenge) marks.push(pill('challenge', 'accent'));
  if (offer.player_stolen) {
    marks.push(pill(`you field a ${offer.player_stolen}`, 'accent'));
  }
  if (offer.bonus_percent) {
    marks.push(pill(`+${offer.bonus_percent}% Ore`, 'ore'));
  }
  return marks;
}

/* One picture per map, fetched once. They run to a hundred kilobytes and
 * they do not change, so asking for them again on every redraw would be
 * the most expensive thing this screen does.
 *
 * Kept to the last few, because there are seven hundred maps installed
 * and a launcher left open through a long run would otherwise hold every
 * one it had ever been offered. Insertion order is eviction order, which
 * is what a Map already gives. */
const previews = new Map();
const KEEP_PREVIEWS = 24;

function keepPreview(path, uri) {
  previews.set(path, uri);
  while (previews.size > KEEP_PREVIEWS) {
    previews.delete(previews.keys().next().value);
  }
}

async function loadPreviews(offers) {
  await Promise.all(offers
    .filter((offer) => offer.has_preview && !previews.has(offer.map_path))
    .map(async (offer) => {
      try {
        const answer = await call('skirmish.preview', {
          map_path: offer.map_path,
        });
        keepPreview(offer.map_path, answer.uri || '');
      } catch {
        keepPreview(offer.map_path, '');
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

/**
 * A button that asks once.
 *
 * Ending a run cannot be undone and there are no dialogs on these
 * screens, so the button becomes the question and the second press is the
 * answer -- the same bargain the run list makes before forgetting one.
 */
function giveUpButton(run) {
  let asked = false;
  const node = button('Give up run', {
    variant: 'danger',
    disabled: !run.active,
    onClick: async () => {
      if (!asked) {
        asked = true;
        node.textContent = 'End this run?';
        return;
      }
      await act('skirmish.give_up');
    },
  });
  return node;
}

/* Whether the armies are on show. Kept outside render so that opening the
 * panel survives the redraw that follows buying something -- which is the
 * moment the list changes and the one worth watching it through. */
let showingArmies = false;

function header(run) {
  return row([
    el('div', { class: 'row' }, [
      el('strong', { text: run.progress }),
      pill(`${run.player.display}`, 'accent'),
      pill(`ally: ${run.ally.display}`),
      el('span', { class: 'ore', text: `${count(run.coins)} Ore` }),
    ]),
    el('div', { class: 'row' }, [
      run.warmup && button('Skip warmup', {
        variant: 'quiet',
        onClick: () => act('skirmish.skip_warmup'),
      }),
      giveUpButton(run),
    ]),
  ], { spread: true });
}

/**
 * The line above the shelf: what you own, and another shelf for Ore.
 *
 * Both belong here rather than in the title bar. They are what a player
 * does about the eight rows underneath -- check what is already bought,
 * or pay to be dealt eight others -- and a button for a shelf reads
 * where the shelf is.
 */
function shopBar(run) {
  const price = run.reroll_price || 0;
  return row([
    button(showingArmies ? 'Hide upgrades' : 'Show upgrades', {
      variant: 'quiet',
      onClick: () => {
        showingArmies = !showingArmies;
        refresh();
      },
    }),
    el('div', { class: 'row' }, [
      run.rerolls
        ? el('span', {
          class: 'muted',
          text: run.rerolls === 1 ? '1 reroll' : `${run.rerolls} rerolls`,
        })
        : null,
      el('span', { class: 'ore', text: `${count(price)} Ore` }),
      button('Reroll shelf', {
        disabled: !run.active || run.coins < price,
        title: 'Deal another shelf. What is bought stays bought.',
        onClick: () => act('skirmish.reroll'),
      }),
    ]),
  ], { spread: true });
}

/** One army's card: who it is, and every upgrade it carries by name. */
function armyCard(army, { title, note } = {}) {
  const carried = army.upgrades || [];
  return card({
    title: title || army.display,
    body: carried.length
      ? note || ''
      : `${note ? `${note} ` : ''}Nothing bought yet.`,
    pills: carried.map((one) => pill(
      one.stacks > 1 ? `${one.name} x${one.stacks}` : one.name,
    )),
    // The effect lines are long and there are many of them, so they are
    // what the card says when it is pointed at rather than what it shows.
    title_attr: carried.map((one) => one.effect).filter(Boolean).join('\n'),
  });
}

/* Three armies, not a table of maps.
 *
 * It used to list every battle on the table, because every one of them
 * arms its own enemies differently. That belongs on the battle's own
 * card, where the choice is being made -- Show upgrades, beside Fight --
 * and this answers the plainer question: what are the three armies in
 * this fight carrying. */
function armiesPanel(armies) {
  if (!armies) return notice('This run has nothing to show yet.');
  const enemies = armies.enemies || [];
  return [
    // Your army and the ally's beside each other, because they are the
    // two halves of one side and what is worth seeing is the difference
    // between them: the ally shops out of its own earnings and its own
    // country's list, so over a run the two grow apart.
    section('Your side', grid([
      armyCard(armies.player, { title: `You — ${armies.player.display}` }),
      armyCard(armies.ally, { title: `Ally — ${armies.ally.display}` }),
    ])),
    section(
      'Enemies',
      enemies.length
        ? grid(enemies.map((enemy) => armyCard(enemy, {
          title: `${enemy.display}${enemy.skill ? ` — ${enemy.skill}` : ''}`,
        })))
        : notice('No battle is chosen yet.'),
    ),
  ];
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
  const armies = showingArmies ? await call('skirmish.armies') : null;
  const parts = [section(null, header(run))];
  if (!run.active) {
    // A run that is over keeps its table on screen with everything on it
    // refused, which reads as a launcher that has stopped working rather
    // than as a run that has stopped.
    parts.push(section(null, notice(
      `This run is over — ${run.status}. Start another on the Setup tab.`,
    )));
  }
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
    // What the shop is offering, and above it the two things you do
    // about a shelf that is not what you wanted: look at what you
    // already own, or pay to be dealt another.
    parts.push(section(null, shopBar(run)));
    if (showingArmies) parts.push(...[].concat(armiesPanel(armies)));
    parts.push(section(
      'Upgrades',
      grid(run.shelf.map((upgrade) => upgradeCard(upgrade, run))),
    ));
  }
  parts.push(section('This run', stats(run.stat_lines)));
  root.replaceChildren(...parts);
}

register('skirmish', render);
