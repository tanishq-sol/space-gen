import type { Locator, Page } from '@playwright/test';

/** Opens the toolbar's More menu (Review scan, Drawings, Present, Export) and returns it. */
export async function openMoreActions(page: Page): Promise<Locator> {
  const trigger = page.getByRole('button', { name: 'More actions' });
  if ((await trigger.getAttribute('aria-expanded')) !== 'true') await trigger.click();
  return page.getByRole('group', { name: 'More actions' });
}

/** Clicks one action in the toolbar's More menu; the menu closes after the click. */
export async function clickMoreAction(page: Page, name: string): Promise<void> {
  const menu = await openMoreActions(page);
  await menu.getByRole('button', { name, exact: true }).click();
}

/** Opens the tool palette's overflow group (Convert Scan, Align Scan, Scan, Levels, Cutaway) and returns it. */
export async function openToolOverflow(page: Page): Promise<Locator> {
  const trigger = page.getByRole('button', { name: 'More tools' });
  if ((await trigger.getAttribute('aria-expanded')) !== 'true') await trigger.click();
  return page.getByRole('group', { name: 'More tools' });
}

/** Clicks one tool in the palette's overflow group, matched by its name or its title. */
export async function clickToolOverflow(page: Page, by: { name?: string; title?: RegExp }, options?: { force?: boolean }): Promise<void> {
  const group = await openToolOverflow(page);
  const target = by.title ? group.getByTitle(by.title) : group.getByRole('button', { name: by.name, exact: true });
  await target.click(options);
}
