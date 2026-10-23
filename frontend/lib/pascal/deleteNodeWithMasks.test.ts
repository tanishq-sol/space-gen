import { beforeEach, describe, expect, it } from 'vitest';
import { clearSceneHistory, useScene, type AnyNode } from '@pascal-app/core';
import { createItemNode } from './itemEditing';
import { undoSceneAction } from './sceneBridge';
import { findScanNode, scanMetadata } from './nodes';
import { deleteNodeWithMasks } from '@/lib/splat/splatMasking';

const mask = (id: string, itemId: string) => ({ id, itemId, obb: { center: [0, 0.5, 0], size: [1, 1, 1], yaw: 0 }, feather: 0.05, enabled: true });
const masks = () => (scanMetadata(findScanNode()!).maskRegions || []).map((m) => m.id);

describe('deleteNodeWithMasks', () => {
  beforeEach(() => {
    const scan = {
      object: 'node', id: 'scan_t', type: 'scan', name: 'Scan', parentId: null, url: '/r.sog', visible: true, opacity: 100,
      position: [0, 0, 0], rotation: [0, 0, 0], scale: 1, layers: { model: false },
      metadata: { format: 'sog', maskRegions: [mask('mask_a', 'item_a'), mask('mask_b', 'item_b')] },
    } as unknown as AnyNode;
    const a = createItemNode({ name: 'A', category: 'chair', src: '/a.glb', dimensions: [1, 1, 1], position: [0, 0, 0] }, 'item_a');
    useScene.getState().applyNodeChanges({ create: [{ node: scan }, { node: a as AnyNode }] });
    clearSceneHistory();
  });

  it('removes the item and its mask in one step, and undo restores both', () => {
    deleteNodeWithMasks('item_a');
    expect(useScene.getState().nodes['item_a' as never]).toBeUndefined();
    expect(masks()).toEqual(['mask_b']);
    undoSceneAction();
    expect(useScene.getState().nodes['item_a' as never]).toBeDefined();
    expect(masks()).toEqual(['mask_a', 'mask_b']);
  });
});
