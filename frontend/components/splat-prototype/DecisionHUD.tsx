'use client';

import React from 'react';
import {
  Activity,
  Layers,
  Box,
  Eye,
  AlertTriangle,
  CheckCircle2,
  FileCode,
  Sparkles,
} from 'lucide-react';

export type EvalOption = 'option_a' | 'option_b' | 'option_c' | 'option_d';

interface DecisionHUDProps {
  currentOption: EvalOption;
  onChangeOption: (opt: EvalOption) => void;
  fps: number;
  splatCount: number;
  format: string;
  isLoaded: boolean;
  itemDepthMode: 'front' | 'behind';
  onChangeDepthMode: (mode: 'front' | 'behind') => void;
  enableMasking: boolean;
  onToggleMasking: (enabled: boolean) => void;
  showOcclusionProxy: boolean;
  onToggleOcclusionProxy: (enabled: boolean) => void;
  itemType: 'chair' | 'sofa' | 'coffee_table';
  onChangeItemType: (type: 'chair' | 'sofa' | 'coffee_table') => void;
}

export const DecisionHUD: React.FC<DecisionHUDProps> = ({
  currentOption,
  onChangeOption,
  fps,
  splatCount,
  format,
  isLoaded,
  itemDepthMode,
  onChangeDepthMode,
  enableMasking,
  onToggleMasking,
  showOcclusionProxy,
  onToggleOcclusionProxy,
  itemType,
  onChangeItemType,
}) => {
  return (
    <div className="absolute top-4 left-4 z-20 flex flex-col gap-3 max-w-sm pointer-events-auto">
      {/* 1. Header & Live Metrics Card */}
      <div className="bg-surface backdrop-blur-md border border-border rounded-xl p-4 shadow-2xl text-text-primary">
        <div className="flex items-center justify-between pb-3 border-b border-border">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-success" />
            <h3 className="font-semibold text-xs text-text-primary">
              Splat & Pascal Integration
            </h3>
          </div>
          <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-success-muted text-success border border-success/30">
            PROTOTYPE
          </span>
        </div>

        {/* Live Metrics Grid */}
        <div className="grid grid-cols-3 gap-2 mt-3 pt-1">
          <div className="bg-surface-elevated p-2 rounded-lg border border-border">
            <div className="flex items-center gap-1 text-[11px] text-text-secondary">
              <Activity className="w-3 h-3 text-success" />
              <span>FPS</span>
            </div>
            <div className="text-base font-bold text-success mt-0.5">
              {currentOption === 'option_c' && isLoaded ? fps : '—'}
            </div>
          </div>

          <div className="bg-surface-elevated p-2 rounded-lg border border-border">
            <div className="flex items-center gap-1 text-[11px] text-text-secondary">
              <Box className="w-3 h-3 text-accent" />
              <span>Splats</span>
            </div>
            <div className="text-sm font-bold text-accent mt-1">
              {isLoaded ? splatCount.toLocaleString() : 'Loading…'}
            </div>
          </div>

          <div className="bg-surface-elevated p-2 rounded-lg border border-border">
            <div className="flex items-center gap-1 text-[11px] text-text-secondary">
              <FileCode className="w-3 h-3 text-accent" />
              <span>Format</span>
            </div>
            <div className="text-[11px] font-semibold text-accent truncate mt-1" title={format}>
              {format || '.sog'}
            </div>
          </div>
        </div>
      </div>

      {/* 2. Architecture Candidates Evaluation Selector */}
      <div className="bg-surface backdrop-blur-md border border-border rounded-xl p-4 shadow-2xl text-text-primary flex flex-col gap-2">
        <label className="text-[11px] font-semibold text-text-primary flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5 text-accent" />
          Evaluate Architecture Candidates
        </label>

        <div className="grid grid-cols-1 gap-1.5 mt-1 text-xs">
          <button
            onClick={() => onChangeOption('option_c')}
            className={`flex items-start gap-2.5 p-2 rounded-lg border text-left transition ${
              currentOption === 'option_c'
                ? 'bg-emerald-950/60 border-success/30 text-emerald-200'
                : 'bg-surface-elevated border-border text-text-primary hover:bg-surface-elevated'
            }`}
          >
            <CheckCircle2 className="w-4 h-4 text-success mt-0.5 shrink-0" />
            <div>
              <div className="font-semibold text-xs flex items-center gap-1.5">
                (c) Dual-Canvas Synced (Recommended)
              </div>
              <p className="text-[11px] text-text-secondary mt-0.5 leading-snug">
                Spark WebGL2 background + Pascal WebGPU foreground. .sog support, OBB masking. FPS above is measured live.
              </p>
            </div>
          </button>

          <button
            onClick={() => onChangeOption('option_a')}
            className={`flex items-start gap-2.5 p-2 rounded-lg border text-left transition ${
              currentOption === 'option_a'
                ? 'bg-red-950/60 border-error text-red-200'
                : 'bg-surface-elevated border-border text-text-primary hover:bg-surface-elevated'
            }`}
          >
            <AlertTriangle className="w-4 h-4 text-error mt-0.5 shrink-0" />
            <div>
              <div className="font-semibold text-xs">(a) Spark inside WebGPURenderer</div>
              <p className="text-[11px] text-text-secondary mt-0.5 leading-snug">
                Attempts Spark on a three/webgpu WebGPURenderer in this browser and shows the actual result.
              </p>
            </div>
          </button>

          <button
            onClick={() => onChangeOption('option_b')}
            className={`flex items-start gap-2.5 p-2 rounded-lg border text-left transition ${
              currentOption === 'option_b'
                ? 'bg-amber-950/60 border-warning text-amber-200'
                : 'bg-surface-elevated border-border text-text-primary hover:bg-surface-elevated'
            }`}
          >
            <AlertTriangle className="w-4 h-4 text-warning mt-0.5 shrink-0" />
            <div>
              <div className="font-semibold text-xs">(b) Force Pascal to WebGL + Spark</div>
              <p className="text-[11px] text-text-secondary mt-0.5 leading-snug">
                Attempts Spark on WebGPURenderer with forceWebGL: true and shows the actual result.
              </p>
            </div>
          </button>

          <button
            onClick={() => onChangeOption('option_d')}
            className={`flex items-start gap-2.5 p-2 rounded-lg border text-left transition ${
              currentOption === 'option_d'
                ? 'bg-purple-950/60 border-accent/80 text-accent'
                : 'bg-surface-elevated border-border text-text-primary hover:bg-surface-elevated'
            }`}
          >
            <FileCode className="w-4 h-4 text-accent mt-0.5 shrink-0" />
            <div>
              <div className="font-semibold text-xs">(d) Native WebGPU Splatting</div>
              <p className="text-[11px] text-text-secondary mt-0.5 leading-snug">
                Shared depth buffer, but no open-source .sog decoder in WGSL; requires custom radix compute sorter.
              </p>
            </div>
          </button>
        </div>
      </div>

      {/* 3. Interactive Depth, Occlusion & Masking Controls */}
      {currentOption === 'option_c' && (
        <div className="bg-surface backdrop-blur-md border border-border rounded-xl p-4 shadow-2xl text-text-primary flex flex-col gap-3">
          <label className="text-[11px] font-semibold text-text-primary flex items-center gap-1.5">
            <Eye className="w-3.5 h-3.5 text-accent" />
            Interactive Depth & Masking Verification
          </label>

          {/* Depth Position Switch */}
          <div className="flex flex-col gap-1">
            <span className="text-[11px] text-text-secondary">GLB Item Depth Placement</span>
            <div className="grid grid-cols-2 gap-1.5 bg-surface-elevated p-1 rounded-lg border border-border">
              <button
                onClick={() => onChangeDepthMode('front')}
                className={`py-1 px-2 rounded text-xs font-medium transition-colors ${
                  itemDepthMode === 'front'
                    ? 'bg-success text-text-primary shadow'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                In Front (Room)
              </button>
              <button
                onClick={() => onChangeDepthMode('behind')}
                className={`py-1 px-2 rounded text-xs font-medium transition-colors ${
                  itemDepthMode === 'behind'
                    ? 'bg-amber-600 text-text-primary shadow'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                Behind Scan Wall
              </button>
            </div>
          </div>

          {/* Model Selector */}
          <div className="flex items-center justify-between text-xs pt-1 border-t border-border">
            <span className="text-text-secondary">Item Model:</span>
            <select
              value={itemType}
              onChange={(e) => onChangeItemType(e.target.value as DecisionHUDProps['itemType'])}
              className="bg-surface-elevated border border-border rounded px-2 py-1 text-text-primary text-xs focus:outline-none focus:border-cyan-500"
            >
              <option value="chair">Modern Chair</option>
              <option value="sofa">Lounge Sofa</option>
              <option value="coffee_table">Coffee Table</option>
            </select>
          </div>

          {/* Depth Occlusion Proxy Toggle */}
          <div className="flex items-center justify-between text-xs pt-1 border-t border-border">
            <div>
              <span className="text-text-primary font-medium">Depth Occlusion Proxy</span>
              <p className="text-[11px] text-text-secondary leading-tight">
                colorWrite: false, depthWrite: true
              </p>
            </div>
            <button
              onClick={() => onToggleOcclusionProxy(!showOcclusionProxy)}
              className={`w-10 h-5 flex items-center rounded-full p-0.5 transition-colors ${
                showOcclusionProxy ? 'bg-accent justify-end' : 'bg-border justify-start'
              }`}
            >
              <span className="w-4 h-4 bg-white rounded-full shadow" />
            </button>
          </div>

          {/* OBB Crop Volume Masking Toggle */}
          <div className="flex items-center justify-between text-xs pt-1 border-t border-border">
            <div>
              <span className="text-text-primary font-medium">Per-Region OBB Masking</span>
              <p className="text-[11px] text-text-secondary leading-tight">
                SplatEdit SDF Box (opacity: 0)
              </p>
            </div>
            <button
              onClick={() => onToggleMasking(!enableMasking)}
              className={`w-10 h-5 flex items-center rounded-full p-0.5 transition-colors ${
                enableMasking ? 'bg-success justify-end' : 'bg-border justify-start'
              }`}
            >
              <span className="w-4 h-4 bg-white rounded-full shadow" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
