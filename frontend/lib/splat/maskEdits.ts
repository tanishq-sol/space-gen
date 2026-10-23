import { SplatEdit, SplatEditSdf, SplatEditSdfType } from '@sparkjsdev/spark';
import type { MaskRegion } from '@/lib/contracts';

type SplatEditInstance = InstanceType<typeof SplatEdit>;

export interface MaskableMesh {
  edits: SplatEditInstance[] | null;
}

/** Mask boxes never reach below the floor (scene y=0) + this margin, so masking an item keeps the floor splats. */
export const MASK_FLOOR_MARGIN = 0.04;

/** Raises the bottom of a mask box to the floor margin (render-time only; the stored OBB is untouched). */
export function clampMaskObbToFloor(obb: MaskRegion['obb']): MaskRegion['obb'] {
  const bottom = obb.center[1] - obb.size[1] / 2;
  const top = obb.center[1] + obb.size[1] / 2;
  if (bottom >= MASK_FLOOR_MARGIN || top <= MASK_FLOOR_MARGIN + 0.01) return obb;
  const height = top - MASK_FLOOR_MARGIN;
  return {
    ...obb,
    center: [obb.center[0], MASK_FLOOR_MARGIN + height / 2, obb.center[2]],
    size: [obb.size[0], height, obb.size[2]],
  };
}

/**
 * Builds one Spark SplatEdit per enabled mask region.
 *
 * Spark evaluates edit SDFs after the SplatMesh's own transform (world space), and the mesh's
 * matrix is the persisted scanToScene. Mask OBBs are therefore authored in scene frame
 * (Y-up, meters, floor y=0) and must not be multiplied by scanToScene again.
 */
export function buildMaskEdits(regions: readonly MaskRegion[]): SplatEditInstance[] {
  const edits: SplatEditInstance[] = [];
  for (const mask of regions) {
    if (mask.enabled === false) continue;
    const obb = clampMaskObbToFloor(mask.obb);
    const sdf = new SplatEditSdf({
      type: SplatEditSdfType.BOX,
      opacity: mask.ghost ? (mask.opacity ?? 0.25) : 0.0,
    });
    sdf.position.set(obb.center[0], obb.center[1], obb.center[2]);
    sdf.rotation.set(0, obb.yaw || 0, 0);
    // Spark box SDFs take half-extents through the object's scale.
    sdf.scale.set(
      Math.max(0.005, obb.size[0] / 2),
      Math.max(0.005, obb.size[1] / 2),
      Math.max(0.005, obb.size[2] / 2),
    );
    sdf.updateMatrixWorld();
    edits.push(new SplatEdit({ sdfs: [sdf], softEdge: mask.feather ?? 0.05, sdfSmooth: 0.02 }));
  }
  return edits;
}

/**
 * Attaches mask edits to a single mesh. The edits are deliberately NOT added to the THREE scene:
 * Spark treats any SplatEdit in the scene graph outside a SplatMesh as a global edit and also
 * applies `mesh.edits`, which would apply every mask twice (ghost opacity 0.25 → 0.0625).
 */
export function applyMaskEdits(mesh: MaskableMesh, regions: readonly MaskRegion[]): SplatEditInstance[] {
  const edits = buildMaskEdits(regions);
  mesh.edits = edits.length > 0 ? edits : null;
  return edits;
}
