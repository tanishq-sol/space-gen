import { test, expect } from '@playwright/test';

test.use({ viewport: { width: 800, height: 450 } });
test.describe('T08: Splat Masking & Replacement Verification', () => {
  test('replacing a chair creates mask, hides splats from 4 angles, toggles ghost mode, resizes, and supports undo/redo', async ({
    page,
  }) => {
    test.setTimeout(250000); const __t0=Date.now();

    // 1. Mock furniture catalog endpoint for reliable E2E assets
    await page.route('**/api/reconstruction/furniture-catalog', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'chair-original-e2e',
            name: 'Original Scanned Chair',
            category: 'chair',
            style: 'Classic',
            dimensions: { width_m: 0.55, depth_m: 0.55, height_m: 0.85 },
            color_preview: '#888888',
            description: 'Original Chair Fixture',
            filename: 'chair.glb',
            url: '/samples/models/chair.glb',
          },
          {
            id: 'chair-replacement-e2e',
            name: 'Modern Replacement Chair',
            category: 'chair',
            style: 'Contemporary',
            dimensions: { width_m: 0.6, depth_m: 0.6, height_m: 0.9 },
            color_preview: '#e07a5f',
            description: 'Replacement Chair Fixture',
            filename: 'chair.glb',
            url: '/samples/models/chair.glb',
          },
        ]),
      })
    );

    // 2. Navigate to editor
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 42');
    await expect(page.getByRole('button', { name: 'Add Catalog Item' })).toBeVisible({ timeout: 20000 });
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 43');

    // 3. Add original chair into the scene
    await page.getByRole('button', { name: 'Add Catalog Item' }).click();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 46');
    await page.getByRole('button', { name: /Original Scanned Chair/i }).click();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 47');
    const originalChair = page.getByRole('button', { name: /Original Scanned Chair/i }).first();
    await expect(originalChair).toBeVisible({ timeout: 10000 });
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 49');

    // 5. Replace original chair with Modern Replacement Chair
    const replaceButton = page.getByRole('button', { name: /Replace \/ Add Catalog Item/i });
    await expect(replaceButton).toBeVisible();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 53');
    await replaceButton.click();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 54');

    const replacementOption = page.getByRole('button', { name: /Modern Replacement Chair/i });
    await expect(replacementOption).toBeVisible({ timeout: 10000 });
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 57');
    await replacementOption.click();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 58');

    // 6. Verify replaced item in hierarchy
    await expect(page.getByRole('button', { name: /Modern Replacement Chair/i }).first()).toBeVisible();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 61');

    // Verify Splat Mask controls appear automatically for the replaced item
    await expect(page.getByText('Splat Mask')).toBeVisible({ timeout: 5000 });
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 64');
    await expect(page.getByText('Masked (0%)')).toBeVisible();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 65');

    const ghostToggleButton = page.getByRole('button', { name: 'Toggle Ghost Mode' });
    await expect(ghostToggleButton).toBeVisible();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 68');
    await expect(ghostToggleButton).toContainText('Show Original (Ghost Mode)');
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 69');

    // 7. Test Undo of Replacement: Restores original chair and removes mask
    const undoButton = page.getByRole('banner').getByTitle('Undo (Ctrl+Z)');
    await expect(undoButton).toBeEnabled();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 73');
    await undoButton.click();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 74');

    // Original chair restored in outliner
    await expect(page.getByRole('button', { name: /Original Scanned Chair/i })).toBeVisible({ timeout: 5000 });
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 77');
    // Mask controls should no longer be present on the unmasked original chair
    await expect(page.getByText('Masked (0%)')).toHaveCount(0);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 79');

    // Test Redo: Re-applies replacement and restores mask
    const redoButton = page.getByRole('banner').getByTitle('Redo (Ctrl+Y)');
    await expect(redoButton).toBeEnabled();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 83');
    await redoButton.click();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 84');

    // Replaced chair restored
    await expect(page.getByRole('button', { name: /Modern Replacement Chair/i }).first()).toBeVisible({ timeout: 5000 });
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 87');
    await expect(page.getByText('Masked (0%)')).toBeVisible();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 88');

    // 8. Assert the masks Spark actually receives (not just the panel text).
    type SplatDebug = {
      hasMesh: boolean;
      globalEdits: number;
      edits: { softEdge: number; sdfs: { type: string; opacity: number; halfExtents: number[] }[] }[];
    };
    const readSplat = () =>
      page.evaluate(() => (window as unknown as { __spaceGenSplat?: () => unknown }).__spaceGenSplat?.() ?? null) as Promise<SplatDebug | null>;

    await expect.poll(async () => (await readSplat())?.edits.length ?? -1, { timeout: 10000 }).toBe(1);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 99');
    let splat = (await readSplat())!;
    expect(splat.hasMesh).toBe(true);
    // Edits must be scoped to the mesh only; a scene-graph copy would apply the mask twice.
    expect(splat.globalEdits).toBe(0);
    expect(splat.edits[0].sdfs).toHaveLength(1);
    expect(splat.edits[0].sdfs[0].type).toBe('box');
    expect(splat.edits[0].sdfs[0].opacity).toBe(0);
    // Original chair is 0.55 m wide -> 0.275 m half-extent.
    expect(splat.edits[0].sdfs[0].halfExtents[0]).toBeCloseTo(0.275, 3);

    // Undo removes the splat edit, redo restores it.
    await undoButton.click();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 111');
    await expect.poll(async () => (await readSplat())?.edits.length ?? -1).toBe(0);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 112');
    await redoButton.click();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 113');
    await expect.poll(async () => (await readSplat())?.edits.length ?? -1).toBe(1);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 114');

    // Fresh evidence screenshots for this run (attached to the report, never reused from disk).
    const viewerCanvas = page.locator('canvas').last();
    const canvasBox = await viewerCanvas.boundingBox();
    const cx = canvasBox ? canvasBox.x + canvasBox.width / 2 : 400;
    const cy = canvasBox ? canvasBox.y + canvasBox.height / 2 : 300;
    const capture = async (name: string) => {
      await page.waitForTimeout(250);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 122');
      await page.screenshot({ path: test.info().outputPath(name) });
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 123');
      await test.info().attach(name, { path: test.info().outputPath(name), contentType: 'image/png' });
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 124');
    };
    const orbit = async (dx: number, dy: number) => {
      await page.mouse.move(cx, cy);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 127');
      await page.mouse.down();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 128');
      await page.mouse.move(cx + dx, cy + dy, { steps: 3 });
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 129');
      await page.mouse.up();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 130');
    };

    await capture('chair-mask-angle-1-front.png');
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 133');
    await orbit(90, -20);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 134');
    await capture('chair-mask-angle-2-perspective.png');
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 135');
    await orbit(90, -10);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 136');
    await capture('chair-mask-angle-3-side.png');
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 137');
    await orbit(0, 120);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 138');
    await capture('chair-mask-angle-4-top.png');
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 139');

    // 9. Ghost mode: one edit at 25% opacity (not 0.25^2 from a duplicated edit).
    await ghostToggleButton.click();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 142');
    await expect(page.getByText('Ghost (25%)')).toBeVisible();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 143');
    await expect(ghostToggleButton).toContainText('Show Original: On (Ghost Mode)');
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 144');
    await expect.poll(async () => (await readSplat())?.edits[0]?.sdfs[0]?.opacity).toBeCloseTo(0.25, 3);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 145');
    splat = (await readSplat())!;
    expect(splat.edits).toHaveLength(1);
    expect(splat.globalEdits).toBe(0);
    await capture('chair-mask-ghost-mode.png');
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 149');

    // Toggle back to Masked (0%)
    await ghostToggleButton.click();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 152');
    await expect(page.getByText('Masked (0%)')).toBeVisible();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 153');
    await expect.poll(async () => (await readSplat())?.edits[0]?.sdfs[0]?.opacity).toBe(0);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 154');

    // 10. Test Mask Resizing Controls & Undo
    const widthInput = page.getByRole('spinbutton', { name: 'Mask Width (m)' });
    await expect(widthInput).toBeVisible();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 158');
    await widthInput.fill('0.85');
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 159');
    await widthInput.blur();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 160');
    await expect(widthInput).toHaveValue('0.85');
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 161');
    await expect.poll(async () => (await readSplat())?.edits[0]?.sdfs[0]?.halfExtents[0]).toBeCloseTo(0.425, 3);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 162');

    // Undo the resize back to 0.55
    await undoButton.click();
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 165');
    await expect(widthInput).toHaveValue('0.55');
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 166');
    await expect.poll(async () => (await readSplat())?.edits[0]?.sdfs[0]?.halfExtents[0]).toBeCloseTo(0.275, 3);
    console.log('T+'+((Date.now()-__t0)/1000).toFixed(1)+' line 167');
  });
});
