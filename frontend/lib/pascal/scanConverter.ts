import {
  BuildingNode,
  DoorNode,
  LevelNode,
  SiteNode,
  SlabNode,
  WallNode,
  WindowNode,
  ZoneNode,
  useScene,
  type AnyNode,
  type AnyNodeId,
} from '@pascal-app/core';
import type {
  DetectionInterpretation,
  MaskRegion,
  OpeningInterpretation,
  RoomInterpretation,
  ScanAsset,
  WallInterpretation,
} from '@/lib/contracts';
import { IDENTITY_SCAN_TO_SCENE } from './scanAlignment';
import { createItemNode } from './itemEditing';
import { nodeIdFor, type ReviewMeta } from '@/lib/interpretation/reviewTypes';

export interface RawScanObject {
  id: string;
  label: string; // e.g. "chair", "sofa", "table"
  category: 'chair' | 'sofa' | 'table' | 'bed' | 'lamp' | 'decor' | 'storage';
  center: [number, number, number];
  dimensions: [number, number, number]; // [width, height, depth]
  rotation?: [number, number, number];
  confidence: number;
  modelUrl?: string;
}

export interface RawScanManifest {
  scanId: string;
  name?: string;
  scanFileUrl: string;
  boundaryPolygon: [number, number][]; // 2D floor polygon coordinates
  wallHeight: number;
  wallThickness?: number;
  openings?: Array<{
    type: 'door' | 'window';
    wallIndex: number;
    offset: number;
    width: number;
    height: number;
    elevation?: number;
  }>;
  detectedObjects: RawScanObject[];
}

export interface ConversionResult {
  createdNodeIds: string[];
  wallCount: number;
  openingCount: number;
  itemCount: number;
  /** Mask regions registered on the scan node (kept under the legacy "exclusion" name for callers). */
  exclusionBoxCount: number;
  maskRegions: MaskRegion[];
  levelId: string;
}

/**
 * Built-in default preset manifest for the sample room scan.
 */
export const SAMPLE_ROOM_SCAN_MANIFEST: RawScanManifest = {
  scanId: 'scan_preset_studio',
  name: 'Studio Apartment Room Scan',
  scanFileUrl: '/Hurstville_Museum_Gallery.sog',
  wallHeight: 3.0,
  wallThickness: 0.2,
  boundaryPolygon: [
    [-4.0, -3.0],
    [4.0, -3.0],
    [4.0, 3.0],
    [-4.0, 3.0],
  ],
  openings: [
    {
      type: 'door',
      wallIndex: 2, // South wall
      offset: 4.0,
      width: 0.95,
      height: 2.1,
    },
    {
      type: 'window',
      wallIndex: 0, // North wall
      offset: 4.0,
      width: 2.0,
      height: 1.3,
      elevation: 0.85,
    },
  ],
  detectedObjects: [
    {
      id: 'detected_sofa_1',
      label: 'Boucle 3-Seater Sofa',
      category: 'sofa',
      center: [-2.0, 0, 0],
      dimensions: [2.2, 0.85, 0.95],
      rotation: [0, 0, 0],
      confidence: 0.94,
      modelUrl: '/samples/models/sofa.glb',
    },
    {
      id: 'detected_coffee_table_1',
      label: 'Walnut Coffee Table',
      category: 'table',
      center: [-2.0, 0, 1.2],
      dimensions: [1.1, 0.45, 0.6],
      rotation: [0, 0, 0],
      confidence: 0.91,
      modelUrl: '/samples/models/coffee_table.glb',
    },
    {
      id: 'detected_dining_table_1',
      label: 'Oak Dining Table',
      category: 'table',
      center: [2.0, 0, 0],
      dimensions: [1.8, 0.75, 0.9],
      rotation: [0, 0, 0],
      confidence: 0.96,
      modelUrl: '/samples/models/dining_table.glb',
    },
    {
      id: 'detected_chair_1',
      label: 'Dining Chair North',
      category: 'chair',
      center: [2.0, 0, -0.75],
      dimensions: [0.55, 0.85, 0.55],
      rotation: [0, 0, 0],
      confidence: 0.89,
      modelUrl: '/samples/models/chair.glb',
    },
    {
      id: 'detected_chair_2',
      label: 'Dining Chair South',
      category: 'chair',
      center: [2.0, 0, 0.75],
      dimensions: [0.55, 0.85, 0.55],
      rotation: [0, Math.PI, 0],
      confidence: 0.89,
      modelUrl: '/samples/models/chair.glb',
    },
  ],
};


const MODEL_BY_CATEGORY: Record<string, string> = {
  sofa: '/samples/models/sofa.glb',
  chair: '/samples/models/chair.glb',
  table: '/samples/models/dining_table.glb',
};
const FALLBACK_MODEL = '/samples/models/coffee_table.glb';

export function fallbackModelFor(category: string): string {
  return MODEL_BY_CATEGORY[category] ?? FALLBACK_MODEL;
}

export interface ConvertInterpretationOptions {
  /** Level to attach to; defaults to the first level, creating site/building/level if none exists. */
  levelId?: string;
  /** Registers the background scan node (when absent) so detection masks have somewhere to live. */
  scan?: ScanAsset | null;
  /** Existing masks (e.g. manifest.maskRegions); matched to detections by id, others kept as-is. */
  maskRegions?: MaskRegion[];
  /** Resolves a model URL for a detection; defaults to a category-based sample model. */
  modelUrlFor?: (detection: DetectionInterpretation) => string | undefined;
}

function reviewMeta(
  base: Omit<ReviewMeta, 'status' | 'provenance'>,
  provenance: 'auto' | 'user',
  status?: ReviewMeta['status'],
): ReviewMeta {
  return { ...base, provenance, status: status ?? (provenance === 'user' ? 'corrected' : 'auto') };
}

/**
 * Converts a RoomInterpretation into Pascal nodes in ONE scene transaction (single undo step):
 * a floor slab, a room zone, walls, door/window children and one movable item per detection,
 * plus a MaskRegion on the scan node for each detection. Pascal ids are prefixed from the
 * interpretation id (`wall_<id>`) and the link back is kept in `metadata.review`.
 */
export function convertInterpretationToNodes(
  interpretation: RoomInterpretation,
  options: ConvertInterpretationOptions = {},
): ConversionResult {
  const scene = useScene.getState();
  const nodes = scene.nodes as Record<string, any>;
  const creates: Array<{ node: AnyNode; parentId?: AnyNodeId }> = [];
  const updates: Array<{ id: AnyNodeId; data: any }> = [];
  const createdNodeIds: string[] = [];
  const add = (node: any, parentId?: string) => {
    creates.push({ node, parentId: parentId as AnyNodeId | undefined });
    createdNodeIds.push(node.id);
  };

  let levelId = options.levelId || (Object.values(nodes).find((n) => n?.type === 'level')?.id as string | undefined);
  if (!levelId) {
    const site = SiteNode.parse({ id: 'site_default', name: 'SpaceGen Project' });
    const building = BuildingNode.parse({ id: 'building_default', name: 'Building' });
    const level = LevelNode.parse({ id: 'level_main', name: 'Ground Floor', level: 0 });
    add(site);
    add(building, site.id);
    add(level, building.id);
    levelId = level.id;
  }

  const outline = interpretation.outline;
  if (outline.length >= 3) {
    add(SlabNode.parse({ id: 'slab_room', name: 'Floor', polygon: outline }), levelId);
    add(ZoneNode.parse({ id: 'zone_room', name: 'Room', polygon: outline }), levelId);
  }

  const wallNodeIds = new Map<string, string>();
  for (const wall of interpretation.walls) {
    const id = nodeIdFor('wall', wall.id);
    wallNodeIds.set(wall.id, id);
    add(
      {
        ...WallNode.parse({
          id,
          name: `Wall ${wallNodeIds.size}`,
          start: [wall.start[0], wall.start[2]],
          end: [wall.end[0], wall.end[2]],
          height: wall.height,
          thickness: wall.thickness,
        }),
        metadata: { review: reviewMeta({ sourceId: wall.id, kind: 'wall', confidence: wall.confidence }, wall.provenance) },
      },
      levelId,
    );
  }

  let openingCount = 0;
  for (const opening of interpretation.openings) {
    const wallNodeId = wallNodeIds.get(opening.wallId);
    if (!wallNodeId) continue;
    const type = opening.kind === 'window' ? 'window' : 'door';
    const schema = type === 'window' ? WindowNode : DoorNode;
    add(
      {
        ...(schema as any).parse({
          id: nodeIdFor(type, opening.id),
          name: opening.kind === 'window' ? 'Window' : opening.kind === 'door' ? 'Door' : 'Opening',
          wallId: wallNodeId,
          position: [opening.offset, opening.sill + opening.height / 2, 0],
          width: opening.width,
          height: opening.height,
        }),
        metadata: {
          review: reviewMeta(
            { sourceId: opening.id, kind: 'opening', confidence: opening.confidence, openingKind: opening.kind, sill: opening.sill },
            opening.provenance,
          ),
        },
      },
      wallNodeId,
    );
    openingCount++;
  }

  const providedMasks = options.maskRegions ?? [];
  const masks: MaskRegion[] = [];
  const usedMaskIds = new Set<string>();
  for (const det of interpretation.detections) {
    const itemId = nodeIdFor('item', det.id);
    const [sx, sy, sz] = det.obb.size;
    const maskId = det.maskRegionId || `mask_${itemId}`;
    const provided = providedMasks.find((m) => m.id === maskId);
    masks.push({
      feather: 0.05,
      ghost: false,
      opacity: 0,
      ...provided,
      id: maskId,
      obb: det.obb,
      enabled: det.status !== 'rejected',
      itemId,
      detectionId: det.id,
    });
    usedMaskIds.add(maskId);
    const src = options.modelUrlFor?.(det) ?? fallbackModelFor(det.category);
    const item = createItemNode(
      {
        name: det.label,
        category: det.category,
        src,
        dimensions: [sx, sy, sz],
        position: [det.obb.center[0], det.obb.center[1] - sy / 2, det.obb.center[2]],
        rotation: [0, det.obb.yaw, 0],
        parentId: levelId,
      },
      itemId,
    );
    add(
      {
        ...item,
        visible: det.status !== 'rejected',
        metadata: {
          detectionId: det.id,
          maskRegionId: maskId,
          review: reviewMeta(
            { sourceId: det.id, kind: 'detection', confidence: det.confidence, category: det.category },
            det.provenance,
            det.status,
          ),
        },
      },
      levelId,
    );
  }
  for (const mask of providedMasks) if (!usedMaskIds.has(mask.id)) masks.push(mask);

  const existingScan = Object.values(nodes).find((n) => n?.type === 'scan');
  if (existingScan) {
    const kept = ((existingScan.metadata?.maskRegions ?? []) as MaskRegion[]).filter((m) => !usedMaskIds.has(m.id));
    updates.push({ id: existingScan.id, data: { metadata: { ...(existingScan.metadata || {}), maskRegions: [...kept, ...masks] } } });
  } else if (options.scan?.url?.trim()) {
    add({
      id: 'scan_room',
      type: 'scan',
      name: 'Room scan',
      url: options.scan.url,
      visible: true,
      opacity: 100,
      position: [0, 0, 0],
      rotation: [0, 0, 0],
      scale: 1,
      layers: { model: false },
      metadata: {
        format: options.scan.format,
        scanToScene: options.scan.scanToScene ?? [...IDENTITY_SCAN_TO_SCENE],
        maskRegions: masks,
      },
    }, levelId);
  }

  scene.applyNodeChanges({ create: creates, update: updates });

  return {
    createdNodeIds,
    wallCount: interpretation.walls.length,
    openingCount,
    itemCount: interpretation.detections.length,
    exclusionBoxCount: masks.length,
    maskRegions: masks,
    levelId,
  };
}

/** Adapts the legacy raw scan manifest to a RoomInterpretation (offsets are wall-start to opening centre). */
export function manifestToInterpretation(manifest: RawScanManifest): RoomInterpretation {
  const poly = manifest.boundaryPolygon;
  const height = manifest.wallHeight || 3;
  const thickness = manifest.wallThickness || 0.2;
  const walls: WallInterpretation[] = poly.map((start, i) => {
    const end = poly[(i + 1) % poly.length];
    return {
      id: `scan_${i}`,
      start: [start[0], 0, start[1]],
      end: [end[0], 0, end[1]],
      height,
      thickness,
      confidence: 1,
      provenance: 'auto',
    };
  });
  const openings: OpeningInterpretation[] = (manifest.openings ?? [])
    .filter((o) => walls[o.wallIndex])
    .map((o, i) => ({
      id: `scan_opening_${i}`,
      wallId: walls[o.wallIndex].id,
      kind: o.type,
      offset: o.offset,
      width: o.width,
      height: o.height,
      sill: o.elevation ?? 0,
      confidence: 1,
      provenance: 'auto',
    }));
  const detections: DetectionInterpretation[] = manifest.detectedObjects.map((obj) => ({
    id: obj.id,
    category: obj.category,
    label: obj.label,
    obb: {
      center: [obj.center[0], obj.center[1] + obj.dimensions[1] / 2, obj.center[2]],
      size: obj.dimensions,
      yaw: obj.rotation?.[1] ?? 0,
    },
    confidence: obj.confidence,
    maskRegionId: null,
    status: 'auto',
    provenance: 'auto',
  }));
  return {
    provenance: 'auto',
    floor: { normal: [0, 1, 0], constant: 0, provenance: 'auto' },
    ceilingHeight: height,
    outline: poly,
    walls,
    openings,
    detections,
  };
}

/** Legacy entry point used by the "Scan to editable" dialog; delegates to the interpretation converter. */
export function convertScanToEditableNodes(
  manifest: RawScanManifest,
  options?: { levelId?: string; eraseUnderlyingSplats?: boolean },
): ConversionResult {
  const result = convertInterpretationToNodes(manifestToInterpretation(manifest), {
    levelId: options?.levelId,
    modelUrlFor: (det) => manifest.detectedObjects.find((o) => o.id === det.id)?.modelUrl,
  });
  if (options?.eraseUnderlyingSplats === false) {
    const scan = Object.values(useScene.getState().nodes as Record<string, any>).find((n) => n?.type === 'scan');
    if (scan) {
      const ids = new Set(result.maskRegions.map((m) => m.id));
      useScene.getState().applyNodeChanges({
        update: [{ id: scan.id, data: { metadata: { ...scan.metadata, maskRegions: (scan.metadata?.maskRegions ?? []).filter((m: MaskRegion) => !ids.has(m.id)) } } as any }],
      });
    }
  }
  return result;
}
