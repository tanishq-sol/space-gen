'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useViewer } from '@pascal-app/viewer';
import { useEditor } from '@/lib/pascal/pascalEditor';
import { armArchitecturalTool, type ArchitecturalTool } from '@/components/viewer/ArchitecturalTools';
import {
  MousePointer,
  Square,
  Grid3X3,
  Shapes,
  Armchair,
  Crop,
  Eraser,
  Eye,
  EyeOff,
  Layers,
  Scissors,
  Sparkles,
  Crosshair,
  DoorOpen,
  AppWindow,
  Ruler,
  Ellipsis,
} from 'lucide-react';

type ToolIcon = typeof Square;

const PASCAL_TOOLS: Array<{ tool: ArchitecturalTool; label: string; title: string; Icon: ToolIcon }> = [
  { tool: 'wall', label: 'Wall', title: 'Draw a wall, snapped to scan corners and wall faces', Icon: Square },
  { tool: 'slab', label: 'Slab', title: 'Draw a floor slab', Icon: Grid3X3 },
  { tool: 'door', label: 'Door', title: 'Place a door on a wall', Icon: DoorOpen },
  { tool: 'window', label: 'Window', title: 'Place a window on a wall', Icon: AppWindow },
  { tool: 'measurement', label: 'Measure', title: 'Measure a distance (scan estimate)', Icon: Ruler },
];

export type ActiveTool =
  | 'select'
  | 'wall'
  | 'slab'
  | 'zone'
  | 'item'
  | 'splat-crop'
  | 'splat-eraser';

interface EditorToolbarProps {
  activeTool: ActiveTool;
  onSelectTool: (tool: ActiveTool) => void;
  onOpenConvertModal?: () => void;
  isAligningScan?: boolean;
  onToggleScanAlignment?: () => void;
}

const TOOL =
  'relative flex h-12 w-14 flex-col items-center justify-center gap-0.5 rounded-xl text-[11px] leading-none text-slate transition-colors duration-150 hover:bg-ink/5 hover:text-ink max-lg:h-11 max-lg:w-11 xl:w-16';
const TOOL_ON = 'bg-ink/[0.07] font-semibold text-ink after:absolute after:bottom-1 after:left-4 after:right-4 after:h-0.5 after:rounded-full after:bg-navy';
const MENU_ITEM =
  'flex h-9 w-full items-center gap-2 rounded-control px-2 text-left text-[13px] text-ink hover:bg-ink/5 max-lg:h-11';

/** Bottom tool palette: the editing tools, with the rarely used scan and view tools in an overflow group. */
export function EditorToolbar({ activeTool, onSelectTool, onOpenConvertModal, isAligningScan, onToggleScanAlignment }: EditorToolbarProps) {
  const levelMode = useViewer((state) => state.levelMode);
  const setLevelMode = useViewer((state) => state.setLevelMode);
  const wallMode = useViewer((state) => state.wallMode);
  const setWallMode = useViewer((state) => state.setWallMode);
  const showScans = useViewer((state) => state.showScans);
  const setShowScans = useViewer((state) => state.setShowScans);

  const pascalMode = useEditor((state) => state.mode);
  const pascalTool = useEditor((state) => state.tool);
  const activePascalTool = pascalMode === 'build' ? pascalTool : null;
  const selectTool = (tool: ActiveTool) => {
    armArchitecturalTool(null);
    onSelectTool(tool);
  };

  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!moreOpen) return;
    const close = (event: PointerEvent) => {
      if (!moreRef.current?.contains(event.target as Node)) setMoreOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMoreOpen(false);
    };
    document.addEventListener('pointerdown', close);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', close);
      document.removeEventListener('keydown', onKey);
    };
  }, [moreOpen]);

  const cycleLevelMode = () => {
    if (levelMode === 'stacked') setLevelMode('exploded');
    else if (levelMode === 'exploded') setLevelMode('solo');
    else setLevelMode('stacked');
  };

  const toolButton = (key: string, label: string, title: string, Icon: ToolIcon, on: boolean, onClick: () => void, pressed?: boolean) => (
    <button
      key={key}
      type="button"
      title={title}
      aria-label={label}
      aria-pressed={pressed}
      onClick={onClick}
      className={`${TOOL} ${on ? TOOL_ON : ''}`}
    >
      <Icon size={20} aria-hidden />
      <span className="max-xl:hidden">{label}</span>
    </button>
  );

  const divider = <div className="mx-1 h-8 w-px self-center bg-hairline max-lg:hidden" aria-hidden />;

  return (
    <div
      role="toolbar"
      aria-label="Tools"
      className="glass absolute bottom-[calc(var(--sheet-h,0px)+16px)] left-1/2 z-30 flex max-w-[calc(100%-16px)] -translate-x-1/2 items-center gap-0.5 rounded-2xl p-1.5 lg:bottom-4"
    >
      {toolButton('select', 'Select', 'Select & Transform Tool (V)', MousePointer, activeTool === 'select' && !activePascalTool, () => selectTool('select'))}

      {PASCAL_TOOLS.map(({ tool, label, title, Icon }) =>
        toolButton(tool, label, title, Icon, activePascalTool === tool, () => armArchitecturalTool(activePascalTool === tool ? null : tool), activePascalTool === tool),
      )}

      {toolButton('zone', 'Zone', 'Zone Definition Tool (Z)', Shapes, activeTool === 'zone', () => selectTool('zone'))}
      {toolButton('item', 'Item', 'Furniture & Door/Window Placement (I)', Armchair, activeTool === 'item', () => selectTool('item'))}

      {divider}

      {toolButton('splat-crop', 'Crop box', 'Splat Bounding-Box Erasure Crop Tool (SuperSplat)', Crop, activeTool === 'splat-crop', () => selectTool('splat-crop'))}
      {toolButton('splat-eraser', 'Eraser', 'Splat Eraser Brush (SuperSplat)', Eraser, activeTool === 'splat-eraser', () => selectTool('splat-eraser'))}

      {divider}

      {/* Overflow: scan conversion, alignment, layers and cutaway */}
      <div ref={moreRef} className="relative">
        <button
          type="button"
          aria-label="More tools"
          aria-haspopup="true"
          aria-expanded={moreOpen}
          onClick={() => setMoreOpen((open) => !open)}
          className={`${TOOL} ${moreOpen || isAligningScan || wallMode === 'cutaway' ? 'bg-ink/[0.07] text-ink' : ''}`}
        >
          <Ellipsis size={20} aria-hidden />
          <span className="max-xl:hidden">More</span>
        </button>
        {moreOpen && (
          <div role="group" aria-label="More tools" className="absolute bottom-full right-0 mb-2 w-60 rounded-panel border border-hairline bg-paper p-1.5 shadow-float">
            {onOpenConvertModal && (
              <button
                type="button"
                title="Convert Scan to Editable Space (Extract Walls & Furniture)"
                onClick={() => { setMoreOpen(false); onOpenConvertModal(); }}
                className={MENU_ITEM}
              >
                <Sparkles size={16} aria-hidden className="text-slate" />
                Convert Scan
              </button>
            )}
            {onToggleScanAlignment && (
              <button
                type="button"
                title="Align scan to the floor, real-world scale, and room axes"
                aria-pressed={!!isAligningScan}
                onClick={() => { setMoreOpen(false); onToggleScanAlignment(); }}
                className={`${MENU_ITEM} ${isAligningScan ? 'bg-ink/[0.07] font-semibold' : ''}`}
              >
                <Crosshair size={16} aria-hidden className="text-slate" />
                Align Scan
              </button>
            )}
            <button
              type="button"
              title={`Scan Overlay: ${showScans ? 'Visible (Click to hide)' : 'Hidden (Click to show)'}`}
              aria-pressed={showScans}
              onClick={() => setShowScans(!showScans)}
              className={MENU_ITEM}
            >
              {showScans ? <Eye size={16} aria-hidden className="text-slate" /> : <EyeOff size={16} aria-hidden className="text-slate" />}
              Scan
              <span className="ml-auto text-[11px] text-slate">{showScans ? 'Shown' : 'Hidden'}</span>
            </button>
            <button
              type="button"
              title={`Level Mode: ${levelMode} (Click to cycle)`}
              onClick={cycleLevelMode}
              className={MENU_ITEM}
            >
              <Layers size={16} aria-hidden className="text-slate" />
              <span>Levels</span>
              <span className="ml-auto text-[11px] capitalize text-slate">{levelMode}</span>
            </button>
            <button
              type="button"
              title={`Wall Cutaway / X-Ray: ${wallMode === 'cutaway' ? 'Active' : 'Off'}`}
              aria-pressed={wallMode === 'cutaway'}
              onClick={() => setWallMode(wallMode === 'cutaway' ? 'up' : 'cutaway')}
              className={`${MENU_ITEM} ${wallMode === 'cutaway' ? 'bg-ink/[0.07] font-semibold' : ''}`}
            >
              <Scissors size={16} aria-hidden className="text-slate" />
              Cutaway
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
