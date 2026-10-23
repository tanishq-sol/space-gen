'use client';

import React from 'react';
import { useNavigation, type NavMode, type ViewMode } from '@/lib/navigation/navigationStore';
import { useScene } from '@pascal-app/core';
import { NO_WALLS_HINT, planCollider, type NavNode } from '@/lib/navigation/room';
import { useRoomNavigation } from '@/lib/navigation/useRoom';

const VIEW_MODES: Array<{ id: ViewMode; label: string; title: string }> = [
  { id: 'splat', label: 'Splat', title: 'Gaussian splat only (editable nodes stay invisible but still collide and pick)' },
  { id: 'mesh', label: 'Mesh', title: 'Editable room and objects only' },
  { id: 'both', label: 'Both', title: 'Splat with the editable layer on top' },
];
const NAV_MODES: Array<{ id: NavMode; label: string; title: string }> = [
  { id: 'orbit', label: 'Orbit', title: 'Orbit, pan and zoom' },
  { id: 'walk', label: 'Walk', title: 'First-person walk with collisions' },
];

function Segment<T extends string>({ label, value, options, onChange, testId }: {
  label: string;
  value: T | null;
  options: Array<{ id: T; label: string; title: string }>;
  onChange: (id: T) => void;
  testId?: string;
}) {
  return (
    <div role="group" aria-label={label} data-testid={testId} className="seg">
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          title={option.title}
          aria-pressed={value === option.id}
          onClick={() => onChange(option.id)}
          className="seg-item"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** Splat / Mesh / Both. Read from the store here so a change re-renders only this control. */
export function ViewModeSegment({ testId = 'view-mode' }: { testId?: string }) {
  const viewMode = useNavigation((s) => s.viewMode);
  const setViewMode = useNavigation((s) => s.setViewMode);
  return <Segment label="View mode" testId={testId} value={viewMode} options={VIEW_MODES} onChange={setViewMode} />;
}

/** Orbit / Walk. */
export function NavModeSegment({ testId = 'nav-mode' }: { testId?: string }) {
  const navMode = useNavigation((s) => s.navMode);
  const setNavMode = useNavigation((s) => s.setNavMode);
  return <Segment label="Navigation" testId={testId} value={navMode} options={NAV_MODES} onChange={setNavMode} />;
}

/** Interior / Exterior (designers only). */
export function SceneKindSegment({ testId = 'scene-kind' }: { testId?: string }) {
  const { kind: sceneKind, detected: detectedKind } = useRoomNavigation();
  const override = useNavigation((s) => s.sceneKindOverride);
  const setOverride = useNavigation((s) => s.setSceneKindOverride);
  return (
    <Segment
      label="Scene kind"
      testId={testId}
      value={sceneKind}
      options={[
        { id: 'interior', label: 'Interior', title: `Stay inside the room${override === null && detectedKind === 'interior' ? ' (auto)' : ''}` },
        { id: 'exterior', label: 'Exterior', title: `Free camera outside the building${override === null && detectedKind === 'exterior' ? ' (auto)' : ''}` },
      ]}
      onChange={(kind) => setOverride(kind === detectedKind ? null : kind)}
    />
  );
}

interface NavigationOverlayProps {
  /** Shows the Interior/Exterior toggle (designers only). */
  editable?: boolean;
  /** The editor keeps the segmented controls in its toolbar and only shows the walk hint here. */
  hintOnly?: boolean;
}

/** View mode (Splat / Mesh / Both), navigation (Orbit / Walk), scene kind, and the walk controls hint. */
export function NavigationOverlay({ editable = false, hintOnly = false }: NavigationOverlayProps) {
  // Read here, not in the viewers, so scene edits re-render only this small overlay.
  const noWallCollision = useScene((state) => planCollider(state.nodes as unknown as Record<string, NavNode | undefined>).showHint);
  const navMode = useNavigation((s) => s.navMode);

  const hint = navMode === 'walk' && (
    <div className="pointer-events-none max-w-xs space-y-1 text-right" data-testid="walk-hint">
      <p className="rounded-md bg-surface-elevated px-3 py-1.5 text-xs text-text-primary">
        Click to look around · WASD / arrows move · Shift sprint · Space jump · C crouch · 1/2/3 Splat/Mesh/Both · Esc exit
      </p>
      {noWallCollision && (
        <p role="status" className="rounded-md bg-amber-900/80 px-3 py-1.5 text-xs text-amber-100" data-testid="no-walls-hint">{NO_WALLS_HINT}</p>
      )}
    </div>
  );

  if (hintOnly) {
    return hint ? <div className="pointer-events-none absolute left-1/2 top-[72px] z-40 -translate-x-1/2 text-center">{hint}</div> : null;
  }

  return (
    <div className="pointer-events-auto absolute bottom-4 right-4 z-40 flex flex-col items-end gap-2" data-testid="navigation-overlay">
      {hint}
      <div className="glass rounded-control"><ViewModeSegment /></div>
      <div className="glass rounded-control"><NavModeSegment /></div>
      {editable && <div className="glass rounded-control"><SceneKindSegment /></div>}
    </div>
  );
}
