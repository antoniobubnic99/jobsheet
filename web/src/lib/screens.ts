/**
 * The screens, in the order they are offered, numbered once.
 *
 * The numbers used to live in two places: the rail computed them from the list
 * it draws, and every screen printed its own into its heading. They agreed
 * until the sheet designer was taken out of the rail, and then the rail said
 * `03 Tracker` while the tracker's own heading said `04`. A number that is
 * meant to orient you cannot disagree with itself.
 *
 * So the number is a position in the rail and nothing else. A screen the rail
 * does not offer has no position, gets no number, and its heading simply does
 * without one -- which is the honest answer for a screen you reach from a menu
 * or by typing its address.
 */

/**
 * Screens kept out of the rail.
 *
 * Hidden, not removed: the route still resolves, so `/designer` works if you
 * type it or follow a link, and nothing that depends on a layout stops working.
 * The sheet designer is a thing you use once, when you decide what the workbook
 * should look like; after that it is a door you walk past every day and never
 * open. The workbook carries its own layout, so the design survives without it.
 * The search editor is out for the same reason and reached the same way: one
 * account has one search, described once, revised from the profile menu.
 *
 * Take a key out of this list to put the screen back in the rail; it is
 * renumbered from here, so there is never a gap where a hidden screen was.
 */
export const HIDDEN_FROM_RAIL: readonly string[] = ['designer', 'searchEdit', 'settings'];

export const ALL_SCREENS = [
  { to: '/', key: 'search', end: true },
  { to: '/search/edit', key: 'searchEdit', end: false },
  { to: '/results', key: 'results', end: false },
  { to: '/designer', key: 'designer', end: false },
  { to: '/tracker', key: 'tracker', end: false },
  { to: '/settings', key: 'settings', end: false },
] as const;

export type ScreenKey = (typeof ALL_SCREENS)[number]['key'];

export const RAIL_SCREENS = ALL_SCREENS.filter(
  (screen) => !HIDDEN_FROM_RAIL.includes(screen.key),
).map((screen, index) => ({ ...screen, number: String(index + 1).padStart(2, '0') }));

/** `01`, `02`… for a screen in the rail; empty for one that is not. */
export function screenNumber(key: ScreenKey): string {
  return RAIL_SCREENS.find((screen) => screen.key === key)?.number ?? '';
}

/**
 * Where the profile menu sends you to change what you are looking for.
 *
 * One account has one search, so this is singular on purpose. Until the search
 * editor exists at its own address, an unmatched child route falls through to
 * the search screen -- so the link lands somewhere real either way.
 */
export const MY_SEARCH = '/search/edit';
