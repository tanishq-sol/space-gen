import { chromium } from '@playwright/test';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const logs = [];
page.on('console', m => logs.push(`[${m.type()}] ${m.text().slice(0,300)}`));
page.on('pageerror', e => logs.push(`[pageerror] ${e.message.slice(0,300)}`));
page.on('requestfailed', r => logs.push(`[reqfail] ${r.url()}`));
page.on('response', r => { if (r.status() >= 400) logs.push(`[http ${r.status()}] ${r.url()}`); });
await page.route('**/api/reconstruction/furniture-catalog', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([
 { id: 'a', name: 'Original Scanned Chair', category: 'chair', style: 'C', dimensions: { width_m: 0.55, depth_m: 0.55, height_m: 0.85 }, color_preview: '#888', description: '', filename: 'chair.glb', url: '/samples/models/chair.glb' },
 { id: 'b', name: 'Modern Replacement Chair', category: 'chair', style: 'C', dimensions: { width_m: 0.6, depth_m: 0.6, height_m: 0.9 }, color_preview: '#e07a5f', description: '', filename: 'chair.glb', url: '/samples/models/chair.glb' }]) }));
const t0 = Date.now(); const T = () => ((Date.now()-t0)/1000).toFixed(1);
await page.goto('http://localhost:3100/', { waitUntil: 'domcontentloaded' });
await page.getByRole('button', { name: /Add Catalog Item/ }).click();
await page.getByRole('button', { name: /Original Scanned Chair/i }).click();
await page.getByRole('button', { name: /Replace \/ Add Catalog Item/i }).click();
await page.getByRole('button', { name: /Modern Replacement Chair/i }).click();
console.log(T(), 'replaced');
for (let i = 0; i < 6; i++) {
  await page.waitForTimeout(5000);
  const info = await page.evaluate(() => {
    const s = window.__spaceGenSplat?.();
    const canvases = [...document.querySelectorAll('canvas')].map(c => {
      const r = c.getBoundingClientRect(); const cs = getComputedStyle(c);
      return { w: c.width, h: c.height, rect: [r.x, r.y, r.width, r.height].map(Math.round), z: cs.zIndex, bg: cs.backgroundColor, op: cs.opacity, parentBg: getComputedStyle(c.parentElement).backgroundColor };
    });
    return { splat: s && { hasMesh: s.hasMesh, loaded: s.loadedSplats, edits: s.edits.length }, canvases, gpu: !!navigator.gpu };
  });
  console.log(T(), JSON.stringify(info));
}
await page.screenshot({ path: '/tmp/probe/shot.png' });
console.log(logs.slice(0, 60).join('\n'));
await browser.close();
