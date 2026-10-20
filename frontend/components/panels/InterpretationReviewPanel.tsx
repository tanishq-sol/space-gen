'use client';

import { useMemo, useState } from 'react';
import { useScene } from '@pascal-app/core';
import { redoSceneAction, undoSceneAction } from '@/lib/pascal/sceneBridge';
import {
  addOpening, deleteWall, moveOutlineVertex, moveWall, rejectDetection, relabelDetection, removeOpening,
  resizeOpening, restoreDetection, setDetectionBox, splitWall, verifyElement,
} from '@/lib/interpretation/corrections';
import { confidenceTier, getPlacementWarning, listReviewEntries, TIER_COLORS, type ReviewEntry } from '@/lib/interpretation/review';
import { computeObbForItemNode } from '@/lib/splat/splatMasking';
import { useReviewUi } from '@/lib/interpretation/reviewStore';

type Nodes = Record<string, any>;
const r3 = (v: number) => Math.round(v * 1000) / 1000;
const inputCls = 'w-full rounded border border-border bg-background px-1.5 py-1 text-xs';
const btnCls = 'rounded border border-border px-2 py-1 text-xs hover:bg-background disabled:opacity-40';

function Fields({ labels, values, onApply, applyLabel = 'Apply', testId }: {
  labels: string[]; values: number[]; onApply: (values: number[]) => void; applyLabel?: string; testId: string;
}) {
  const [draft, setDraft] = useState(values.map(String));
  return (
    <form
      className="space-y-1"
      onSubmit={(e) => { e.preventDefault(); onApply(draft.map(Number)); }}
    >
      <div className="grid grid-cols-3 gap-1">
        {labels.map((label, i) => (
          <label key={label} className="text-[10px] text-text-muted">
            {label}
            <input aria-label={`${testId} ${label}`} type="number" step="any" className={inputCls} value={draft[i]}
              onChange={(e) => setDraft(draft.map((v, j) => (j === i ? e.target.value : v)))} />
          </label>
        ))}
      </div>
      <button type="submit" className={btnCls} aria-label={`${applyLabel} ${testId}`}>{applyLabel}</button>
    </form>
  );
}

function run(action: () => void, setError: (m: string) => void) {
  try { action(); setError(''); } catch (e) { setError((e as Error).message); }
}

function Editor({ entry, nodes, setError }: { entry: ReviewEntry; nodes: Nodes; setError: (m: string) => void }) {
  const node = nodes[entry.nodeId];
  const [label, setLabel] = useState(node?.name ?? '');
  const [splitAt, setSplitAt] = useState('');
  if (!node) return null;
  const go = (fn: () => void) => run(fn, setError);

  const verify = entry.status === 'auto' && (
    <button className={btnCls} aria-label="Verify selected" onClick={() => go(() => verifyElement(entry.nodeId))}>Verify</button>
  );

  if (entry.kind === 'wall') {
    const key = `${node.start}|${node.end}`;
    return (
      <div className="space-y-2" data-testid="review-editor">
        <Fields key={key} testId="wall" labels={['start x', 'start z', 'end x', 'end z']} values={[...node.start, ...node.end].map(r3)}
          onApply={([a, b, c, d]) => go(() => moveWall(entry.nodeId, [a, b], [c, d]))} applyLabel="Move wall" />
        <div className="flex items-end gap-1">
          <label className="flex-1 text-[10px] text-text-muted">split at (m)
            <input aria-label="split distance" type="number" step="any" className={inputCls} value={splitAt} placeholder="middle" onChange={(e) => setSplitAt(e.target.value)} />
          </label>
          <button className={btnCls} onClick={() => go(() => { splitWall(entry.nodeId, splitAt === '' ? undefined : Number(splitAt)); setSplitAt(''); })}>Split wall</button>
          <button className={btnCls} onClick={() => go(() => addOpening(entry.nodeId, { kind: 'door', offset: Math.hypot(node.end[0] - node.start[0], node.end[1] - node.start[1]) / 2, width: 0.9, height: 2.1, sill: 0 }))}>Add door</button>
          <button className={btnCls} onClick={() => go(() => addOpening(entry.nodeId, { kind: 'window', offset: Math.hypot(node.end[0] - node.start[0], node.end[1] - node.start[1]) / 2, width: 1.2, height: 1.2, sill: 0.9 }))}>Add window</button>
        </div>
        <div className="flex gap-1">{verify}<button className={btnCls} aria-label="Delete wall" onClick={() => go(() => { deleteWall(entry.nodeId); useReviewUi.getState().select(null); })}>Delete wall</button></div>
      </div>
    );
  }

  if (entry.kind === 'opening') {
    const sill = r3(Math.max(0, node.position[1] - node.height / 2));
    return (
      <div className="space-y-2" data-testid="review-editor">
        <Fields key={`${node.position}|${node.width}|${node.height}`} testId="opening" labels={['offset', 'width', 'height', 'sill']}
          values={[node.position[0], node.width, node.height, sill].map(r3)}
          onApply={([offset, width, height, s]) => go(() => resizeOpening(entry.nodeId, { offset, width, height, sill: s }))} applyLabel="Resize opening" />
        <div className="flex gap-1">{verify}<button className={btnCls} aria-label="Remove opening" onClick={() => go(() => { removeOpening(entry.nodeId); useReviewUi.getState().select(null); })}>Remove</button></div>
      </div>
    );
  }

  const obb = computeObbForItemNode(node);
  const rejected = entry.status === 'rejected';
  return (
    <div className="space-y-2" data-testid="review-editor">
      <div className="flex items-end gap-1">
        <label className="flex-1 text-[10px] text-text-muted">label
          <input aria-label="detection label" className={inputCls} value={label} onChange={(e) => setLabel(e.target.value)} />
        </label>
        <button className={btnCls} aria-label="Relabel detection" onClick={() => go(() => relabelDetection(entry.nodeId, label))}>Relabel</button>
      </div>
      <Fields key={JSON.stringify(obb)} testId="box" labels={['x', 'y', 'z', 'w', 'h', 'd', 'yaw°']}
        values={[...obb.center, ...obb.size, (obb.yaw * 180) / Math.PI].map(r3)}
        onApply={([x, y, z, w, h, d, yaw]) => go(() => setDetectionBox(entry.nodeId, { center: [x, y, z], size: [w, h, d], yaw: (yaw * Math.PI) / 180 }))} applyLabel="Apply box" />
      <div className="flex gap-1">
        {verify}
        {rejected
          ? <button className={btnCls} onClick={() => go(() => restoreDetection(entry.nodeId))}>Restore</button>
          : <button className={btnCls} aria-label="Reject detection" onClick={() => go(() => rejectDetection(entry.nodeId))}>Reject</button>}
      </div>
    </div>
  );
}

function OutlineEditor({ nodes, setError }: { nodes: Nodes; setError: (m: string) => void }) {
  const slab = Object.values(nodes).find((n) => n?.type === 'slab' && n.id === 'slab_room') ?? Object.values(nodes).find((n) => n?.type === 'slab');
  if (!slab) return null;
  return (
    <details className="border-t border-border pt-2">
      <summary className="cursor-pointer text-xs font-medium">Room outline ({slab.polygon.length} vertices)</summary>
      <div className="mt-2 space-y-2">
        {slab.polygon.map((p: [number, number], i: number) => (
          <div key={`${i}|${p}`} className="flex items-end gap-1">
            <span className="w-4 text-[10px] text-text-muted">{i + 1}</span>
            <Fields testId={`vertex ${i + 1}`} labels={['x', 'z']} values={p.map(r3)} onApply={([x, z]) => run(() => moveOutlineVertex(i, [x, z]), setError)} applyLabel="Move vertex" />
          </div>
        ))}
      </div>
    </details>
  );
}

export function InterpretationReviewPanel() {
  const nodes = useScene((s) => s.nodes) as Nodes;
  const open = useReviewUi((s) => s.panelOpen);
  const overlayOn = useReviewUi((s) => s.overlayOn);
  const setOverlayOn = useReviewUi((s) => s.setOverlayOn);
  const selectedId = useReviewUi((s) => s.selectedId);
  const select = useReviewUi((s) => s.select);
  const setPanelOpen = useReviewUi((s) => s.setPanelOpen);
  const [error, setError] = useState('');
  const entries = useMemo(() => listReviewEntries(nodes), [nodes]);
  if (!open) return null;
  const warning = getPlacementWarning(nodes);
  const selected = entries.find((e) => e.nodeId === selectedId);
  const needReview = entries.filter((e) => e.lowConfidence).length;

  return (
    <aside aria-label="Interpretation review" className="absolute right-3 top-14 z-50 flex max-h-[calc(100%-4.5rem)] w-[340px] flex-col gap-2 overflow-y-auto rounded-lg border border-border bg-surface p-3 text-sm shadow-lg">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Review interpretation</h2>
        <button className={btnCls} onClick={() => setPanelOpen(false)} aria-label="Close review">✕</button>
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span data-testid="review-summary">{needReview} need review · {entries.length} items</span>
        <label className="ml-auto flex items-center gap-1"><input type="checkbox" checked={overlayOn} onChange={(e) => setOverlayOn(e.target.checked)} />Overlay</label>
      </div>
      <div className="flex gap-1">
        <button className={btnCls} onClick={undoSceneAction}>Undo</button>
        <button className={btnCls} onClick={redoSceneAction}>Redo</button>
        <button className={btnCls} onClick={() => entries.filter((e) => e.status === 'auto').forEach((e) => verifyElement(e.nodeId))}>Verify all</button>
      </div>
      {warning && <p role="status" data-testid="placement-warning" className="rounded border border-amber-500/50 bg-amber-500/10 p-2 text-xs text-amber-600">{warning}</p>}
      {error && <p role="alert" className="text-xs text-red-500">{error}</p>}
      <ul className="space-y-1" data-testid="review-list">
        {entries.map((entry) => (
          <li key={entry.nodeId} className={`rounded border p-1.5 ${entry.nodeId === selectedId ? 'border-accent' : 'border-border'}`} data-testid="review-row" data-status={entry.status} data-low={entry.lowConfidence}>
            <div className="flex items-center gap-2">
              <span aria-hidden className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: TIER_COLORS[confidenceTier(entry)] }} />
              <button className="flex-1 truncate text-left text-xs" onClick={() => select(entry.nodeId)} aria-label={`Select ${entry.label}`}>
                {entry.label} <span className="text-text-muted">· {entry.kind} · {Math.round(entry.confidence * 100)}%</span>
              </button>
              <span className="text-[10px] uppercase text-text-muted">{entry.status}</span>
              {entry.status === 'auto' && <button className={btnCls} aria-label={`Verify ${entry.label}`} onClick={() => run(() => verifyElement(entry.nodeId), setError)}>Verify</button>}
            </div>
          </li>
        ))}
      </ul>
      {selected && <Editor key={selected.nodeId} entry={selected} nodes={nodes} setError={setError} />}
      <OutlineEditor nodes={nodes} setError={setError} />
    </aside>
  );
}

/** Top-bar entry point; hidden for scenes with no interpretation. */
export function ReviewToggleButton() {
  const nodes = useScene((s) => s.nodes) as Nodes;
  const open = useReviewUi((s) => s.panelOpen);
  const setPanelOpen = useReviewUi((s) => s.setPanelOpen);
  const entries = useMemo(() => listReviewEntries(nodes), [nodes]);
  if (entries.length === 0) return null;
  const pending = entries.filter((e) => e.lowConfidence).length;
  return (
    <button className="rounded border border-border px-3 py-1" aria-pressed={open} onClick={() => setPanelOpen(!open)}>
      Review{pending ? ` (${pending})` : ''}
    </button>
  );
}
