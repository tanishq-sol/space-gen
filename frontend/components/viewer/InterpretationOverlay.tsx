'use client';

import { useMemo } from 'react';
import { useScene } from '@pascal-app/core';
import { confidenceTier, listReviewEntries, TIER_COLORS } from '@/lib/interpretation/review';
import { useReviewUi } from '@/lib/interpretation/reviewStore';

type Nodes = Record<string, any>;

/** Review-mode overlay: walls, openings and detection boxes tinted by confidence tier. */
export function InterpretationOverlay() {
  const panelOpen = useReviewUi((s) => s.panelOpen);
  const overlayOn = useReviewUi((s) => s.overlayOn);
  const selectedId = useReviewUi((s) => s.selectedId);
  const select = useReviewUi((s) => s.select);
  const nodes = useScene((s) => s.nodes) as Nodes;
  const entries = useMemo(() => (panelOpen && overlayOn ? listReviewEntries(nodes) : []), [nodes, panelOpen, overlayOn]);

  return (
    <group name="interpretation-overlay">
      {entries.map((entry) => {
        const node = nodes[entry.nodeId];
        const color = TIER_COLORS[confidenceTier(entry)];
        const selected = entry.nodeId === selectedId;
        const pick = (e: any) => {
          e.stopPropagation();
          select(entry.nodeId);
        };
        const material = (
          <meshBasicMaterial color={color} transparent opacity={selected ? 0.6 : 0.32} depthWrite={false} wireframe={entry.kind === 'detection' && !selected} />
        );
        if (entry.kind === 'detection') {
          if (entry.status === 'rejected') return null;
          const [px, py, pz] = node.position as [number, number, number];
          const [w, h, d] = (node.asset?.dimensions ?? [1, 1, 1]).map((v: number, i: number) => v * Math.abs(node.scale?.[i] ?? 1));
          return (
            <mesh key={entry.nodeId} position={[px, py + h / 2, pz]} rotation={[0, node.rotation?.[1] ?? 0, 0]} onClick={pick} userData={{ review: entry.nodeId }}>
              <boxGeometry args={[w, h, d]} />
              {material}
            </mesh>
          );
        }
        const wall = entry.kind === 'wall' ? node : nodes[node.wallId ?? node.parentId];
        if (!wall) return null;
        const [sx, sz] = wall.start as [number, number];
        const [ex, ez] = wall.end as [number, number];
        const length = Math.hypot(ex - sx, ez - sz) || 0.01;
        const angle = -Math.atan2(ez - sz, ex - sx);
        if (entry.kind === 'wall') {
          return (
            <mesh key={entry.nodeId} position={[(sx + ex) / 2, wall.height / 2, (sz + ez) / 2]} rotation={[0, angle, 0]} onClick={pick} userData={{ review: entry.nodeId }}>
              <boxGeometry args={[length, wall.height, wall.thickness + 0.06]} />
              {material}
            </mesh>
          );
        }
        const along = node.position[0] / length;
        const cx = sx + (ex - sx) * along;
        const cz = sz + (ez - sz) * along;
        return (
          <mesh key={entry.nodeId} position={[cx, node.position[1], cz]} rotation={[0, angle, 0]} onClick={pick} userData={{ review: entry.nodeId }}>
            <boxGeometry args={[node.width, node.height, wall.thickness + 0.12]} />
            {material}
          </mesh>
        );
      })}
    </group>
  );
}
