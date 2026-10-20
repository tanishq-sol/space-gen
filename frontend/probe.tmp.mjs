import { chromium } from '@playwright/test';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
await page.route('**/api/reconstruction/furniture-catalog', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([
 { id: 'a', name: 'Original Scanned Chair', category: 'chair', style: 'C', dimensions: { width_m: 0.55, depth_m: 0.55, height_m: 0.85 }, color_preview: '#888', description: '', filename: 'chair.glb', url: '/samples/models/chair.glb' },
 { id: 'b', name: 'Modern Replacement Chair', category: 'chair', style: 'C', dimensions: { width_m: 0.6, depth_m: 0.6, height_m: 0.9 }, color_preview: '#e07a5f', description: '', filename: 'chair.glb', url: '/samples/models/chair.glb' }]) }));
const t0 = Date.now(); const T = () => ((Date.now()-t0)/1000).toFixed(1);
const settle = async () => { for (let i=0;i<20;i++){ await page.waitForTimeout(1500); } };
await page.goto('http://localhost:3100/');
await page.getByRole('button', { name: 'Import / Scenes' }).click({ force: true });
await page.getByRole('button', { name: /import 3d model/i }).click({ force: true });
await page.getByRole('button', { name: 'Load verified sample room scan' }).click({ force: true });
await settle(); await page.screenshot({ path: '/tmp/verify/p1-scan.png' }); console.log(T(), 'scan');
await page.getByRole('button', { name: /Add Catalog Item/ }).click();
await page.getByRole('button', { name: /Original Scanned Chair/i }).click();
await settle(); await page.screenshot({ path: '/tmp/verify/p2-chair.png' }); console.log(T(), 'chair');
await page.getByRole('button', { name: /Replace \/ Add Catalog Item/i }).click();
await page.getByRole('button', { name: /Modern Replacement Chair/i }).click();
await settle(); await page.screenshot({ path: '/tmp/verify/p3-masked.png' }); console.log(T(), 'masked', JSON.stringify(await page.evaluate(() => window.__spaceGenSplat?.())));
await page.getByRole('button', { name: 'Toggle Ghost Mode' }).click();
await settle(); await page.screenshot({ path: '/tmp/verify/p4-ghost.png' }); console.log(T(), 'ghost');
await browser.close();
