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
for (let i = 0; i < 1; i++) {
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
await page.waitForTimeout(8000);
await page.screenshot({ path: '/tmp/probe/both.png' });
await page.evaluate(() => { document.querySelectorAll('canvas')[1].style.visibility = 'hidden'; });
await page.waitForTimeout(3000);
await page.screenshot({ path: '/tmp/probe/splat-only.png' });
const px = await page.evaluate(() => { const c = document.querySelectorAll('canvas')[0]; const o = document.createElement('canvas'); o.width=c.width; o.height=c.height; const g=o.getContext('2d'); g.drawImage(c,0,0); const d=g.getImageData(0,0,o.width,o.height).data; let lit=0; for (let i=0;i<d.length;i+=4) if (d[i]+d[i+1]+d[i+2]>60) lit++; return lit/(d.length/4); });
console.log('splat canvas lit fraction', px);

await browser.close();
