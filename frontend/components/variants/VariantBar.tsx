'use client';

import { useState } from 'react';
import type { Variant } from '@/lib/contracts';

export interface VariantBarProps {
  variants: Variant[];
  activeId: string;
  onSwitch: (id: string) => void;
  onCreate: (from: 'current' | 'blank') => void;
  onDuplicate: () => void;
  onRename: (name: string) => void;
  onDelete: () => void;
  onCompare: () => void;
}

const btn = 'inline-flex h-7 items-center rounded-control border border-border bg-paper px-2 text-xs text-ink transition-colors hover:bg-ink/5 disabled:opacity-40 disabled:pointer-events-none max-lg:h-10';

export function VariantBar({ variants, activeId, onSwitch, onCreate, onDuplicate, onRename, onDelete, onCompare }: VariantBarProps) {
  const [renaming, setRenaming] = useState<string | null>(null);
  const active = variants.find((v) => v.id === activeId);
  return (
    <div role="group" aria-label="Variants" className="flex flex-wrap items-center gap-1.5 px-0 pt-2 text-sm">
      {renaming === null ? (
        <select aria-label="Active variant" value={activeId} onChange={(e) => onSwitch(e.target.value)} className="h-8 max-w-full rounded-control border border-border bg-paper px-2 text-[13px] max-lg:h-10">
          {variants.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
        </select>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); if (renaming.trim()) onRename(renaming); setRenaming(null); }} className="flex gap-1">
          <input aria-label="Variant name" autoFocus value={renaming} onChange={(e) => setRenaming(e.target.value)} onBlur={() => setRenaming(null)} onKeyDown={(e) => e.key === 'Escape' && setRenaming(null)} className="h-8 w-32 rounded-control border border-border bg-paper px-2 text-[13px]" />
        </form>
      )}
      <button className={btn} onClick={() => onCreate('current')}>New from current</button>
      <button className={btn} onClick={() => onCreate('blank')}>New blank</button>
      <button className={btn} onClick={onDuplicate}>Duplicate</button>
      <button className={btn} onClick={() => setRenaming(active?.name ?? '')}>Rename</button>
      <button className={btn} onClick={onDelete} disabled={variants.length <= 1}>Delete</button>
      <button className={btn} onClick={onCompare} disabled={variants.length < 2}>Compare</button>
    </div>
  );
}
