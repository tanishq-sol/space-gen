# SpaceGen UI redesign plan: "Vellum over blueprint"

Status: plan, not started. Brief from the owner: subtle, Apple-inspired, Liquid Glass / frosted look, white and navy palettes, must not look AI-made.

## 1. The idea (why this look belongs to SpaceGen and no one else)

SpaceGen's users are architects and interior designers working on a scanned room. Their world has two materials that match the brief exactly:

- **Blueprint**: navy ink, white linework, dimension lines. This is the navy palette.
- **Drafting vellum and frosted architectural glass**: a translucent sheet laid over a drawing so you can still see it. This is the frosted glass.

So the interface is a sheet of vellum laid over the scan: the room stays in charge, the controls float on frosted panels above it, and the ink is navy. The one memorable element (the "signature") is the **measurement**: SpaceGen already shows every size as `≈ 3.42 m ±2 cm`. Those labels get a drafted dimension-line style (thin ticks, tabular figures) and appear everywhere sizes appear (object bar, drawings, walls, share page). Everything else stays quiet.

## 2. What is wrong now (measured in the code)

| AI-made tell | Where | Count |
|---|---|---|
| Indigo-to-violet brand gradient, gradient text on "Gen" | logo, headers | 8 uses in 4 files |
| Glow shadows | buttons, logo | 3 files |
| Near-black #06060C ground with one bright accent | whole app | global |
| Tracked-out uppercase labels (`.badge`) | badges, panel headers | 21 uses in 10 files |
| Monospace for ordinary UI text ("Loading Pascal 3D workspace...") | 17 files | 68 uses |
| Accent colour sprayed on chrome | 28 files | 232 uses |
| Internal names in copy ("Pascal", "AI Spatial Workspace Panel") | editor, loaders | several |
| Three fixed opaque columns (280 / viewport / 380) | editor | the scan is boxed in |

Root `/` is the editor itself; there is no front door. `/projects` is a bare list.

## 3. Token system

### Colour (contrast computed, not estimated)

Light (default):

| Role | Hex | Contrast |
|---|---|---|
| Vellum (app ground) | `#F5F7FA` | — |
| Paper (panels, sheets) | `#FFFFFF` | — |
| Ink (primary text) | `#0B1F3A` | 15.4:1 on vellum |
| Navy (primary action fill, selection, brand) | `#1B3A6B` | white label 11.3:1 |
| Slate (secondary text) | `#4D6080` | 5.9:1 on vellum |
| Muted (hints, placeholders) | `#5E6F8A` | 4.75:1 on vellum (the first pick `#6B7C96` failed at 3.95) |
| Hairline (borders, dividers) | `#DDE3EC` | decorative only |
| Error (only for errors) | `#B42318` | 6.1:1 |

The app is **light only** (owner decision). The dark values below are reserved for later and for the walkthrough HUD over the scan; no dark theme ships in this redesign.

Dark (reserved):

| Role | Hex | Contrast |
|---|---|---|
| Night (ground) | `#0A1628` | — |
| Deep (panels) | `#11223D` | — |
| Frost (primary text) | `#EEF2F8` | 16.1:1 |
| Mist (secondary text) | `#A9B6CB` | 8.8:1 |
| Sky (primary action, selection) | `#8FB0E8` | night label on it 8.2:1 |
| Error | `#F97066` | 6.5:1 |

Rules: colour goes on data and the one primary action per view, not on chrome. One or two navy-filled buttons per view, never a row. Navigation shows the active item as a neutral tint, not a coloured pill. Success/warning colours only where state truly needs them.

### Glass (two variants, Apple's two-layer rule)

Glass only on the **functional layer** that floats over the 3D viewport: top toolbar, tool palette, the two side panels, object action bar, walkthrough HUD, dialogs and popovers. Never on cards, list rows, the projects page or panel contents.

| Variant | Recipe | Use |
|---|---|---|
| Regular | `backdrop-filter: blur(24px) saturate(1.4)`, fill white 85%, 1px inner highlight `rgba(255,255,255,.6)` on top edge, hairline border | Anything with text: panels, toolbar, dialogs |
| Clear | blur 12px, fill 30%, 35% dark dimming chip behind icons | Icon-only buttons floating over the scan (walk HUD, view-mode switch) |

Why 85%: worst case is a dark scan pixel behind the panel. At 72% fill slate text drops to 3.5:1, at 85% it is 4.7:1. Clear glass gives ink text only 2.75:1, so it never carries text.

Fallbacks: `prefers-reduced-transparency` → opaque paper/deep; `prefers-contrast: more` → solid fills and stronger borders; at most about 4 glass surfaces on screen; glass panels over the WebGL canvas must not drop viewport FPS (measured in phase 6).

### Type

- **UI**: the platform system stack (`-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI Variable", system-ui, sans-serif`). On a Mac this *is* Apple's type; on Windows it is the native equivalent. Replaces Inter, which every generated app ships.
- **Numbers**: `font-variant-numeric: tabular-nums` for every measurement and count. No monospace for UI text; monospace only for real code or IDs.
- **Display** (projects header, share page title only): one face picked in phase 1 by comparing two candidates on a real screen (Instrument Sans vs Hanken Grotesk). Not a serif, not Inter.
- Scale: 11 / 13 / 15 / 17 / 22 / 28. App body 13–15, nothing below 11. Sentence case everywhere; no tracked uppercase labels.

### Shape, depth, motion

- Radius by hierarchy, not one value: controls 8, panels 14, sheets/dialogs 18.
- Flat content surfaces (hairline or one tone step, no shadow). Only floating glass gets a soft shadow `0 8px 32px rgba(11,31,58,.12)`.
- Motion: one orchestrated moment, when a scan finishes converting and the detected objects lift out of the splat into editable items. Everything else is response motion only (open, close, confirm), 150–250 ms, and all of it off under `prefers-reduced-motion`.

## 4. Editor layout (the main screen)

The scan goes full-bleed; panels float over it as glass sheets that can be collapsed. This is Apple's "extend content beneath the sidebar" rule and the biggest visual change.

```text
Regular (≥1280px)
┌──────────────────────────────────────────────────────────────┐
│ ◖ SpaceGen  Living room ▾       Orbit|Walk  Splat|Mesh|Both   Share ◗ │  ← glass toolbar
│ ┌─────────┐                                       ┌────────────┐ │
│ │ Scene   │                                       │ Ask        │ │
│ │ objects │          3D scan, full bleed          │ proposals  │ │
│ │ walls   │                                       │ variants   │ │
│ │ layers  │       [ ≈ 2.10 m ±2 cm ]  ← signature  │            │ │
│ └─────────┘                                       └────────────┘ │
│          ◖ select  wall  door  window  measure ◗  ← tool palette  │
└──────────────────────────────────────────────────────────────┘

Compact (<1024px): panels become bottom sheets with a grabber; toolbar keeps project name, view mode and Share; the rest goes in a More menu.
```

## 5. The user journey, screen by screen (build order = how often people use it)

1. **Editor** `/editor/[projectId]`: shell above; object action bar with measurement signature; proposals as ghost previews with one navy "Apply" per proposal; drawings panel in the same panel system.
2. **Import a scan** (Convert Scan dialog → interpretation review): one sheet, determinate progress ("Uploading 340/700 MB", "Separating objects 7/12"), plain-language steps, errors that say how to fix them.
3. **Projects** `/projects`: project thumbnails rendered from the scan, last-saved time, one "New project" action. `/` keeps opening the blank editor for now (owner decision).
4. **Walkthrough** (inside the editor): clear-glass icon HUD over the scan, nothing else on screen.
5. **Share / presentation** `/p/[shareToken]`: light, full-bleed scan, display-face title, measurements visible, variant compare swipe.
6. **Landing page** (later, Persuade mode): only once the product screens are done, built from real product screens, not stock.

## 6. Workflow (phases, skills, who does it)

Each phase is one branch and one PR; e2e selectors must keep passing; screenshots at 1440, 1024 and 390 px attached to each PR.

| # | Phase | Output | Skills used |
|---|---|---|---|
| 0 | Context | `PRODUCT.md` (audience, jobs, modes: editor = Operate, share = Experience, landing = Persuade) and `DESIGN.md` describing the current UI as the anti-reference | `impeccable init`, `impeccable document` |
| 1 | Direction | This token system confirmed on one static mock of the editor (light); display face chosen; self-critique ("would I give a different product the same plan?") | `frontend-design`, `apple-design` (improvement mode + `liquid-glass.md`), `taste-skill` app-screens draw with `--keep palette,type`, `ui-ux-pro-max` only as a cross-check (its navy + gold, Inter and testimonial-carousel suggestion was rejected as generic) |
| 2 | Tokens & primitives | Tailwind config + CSS variables (light), `.glass` / `.glass-clear` utilities with fallbacks, Button / Input / Badge / Segmented control / Sheet rebuilt; old gradient, glow, uppercase badge removed | `impeccable typeset`, `colorize`; `vercel-web-design-guidelines` audit |
| 3 | Editor shell | Full-bleed viewport, floating glass toolbar, tool palette, collapsible panels, compact bottom sheets | `apple-design` (toolbars, sidebars, sheets), `impeccable layout`, `adapt` |
| 4 | Screens | Import dialog, interpretation review, projects front door, walkthrough HUD, share page, copy cleanup (no "Pascal", plain verbs) | `impeccable clarify`, `onboard`; `frontend-design` writing rules |
| 5 | Signature & motion | Dimension-line measurement component used everywhere; the one "objects lift out of the scan" moment; reduced-motion path | `impeccable animate`, `delight` (sparingly) |
| 6 | Review & harden | Design review report, a11y and keyboard pass, FPS with glass over the splat (target: no drop vs today), bundle check | `apple-design` review, `impeccable critique` → `audit` → `polish`, `vercel-react-best-practices` |

Frontend phases run on Sonnet subagents in worktrees; anything touching backend (thumbnails for the projects page) on Opus.

## 7. Done means

- Every text pair meets 4.5:1 (3:1 for ≥18px), computed from tokens, including text on glass over the darkest scan pixel.
- No gradient, glow, tracked uppercase or monospace UI text left (`grep` count = 0 outside code/ID displays).
- Glass appears only on the functional layer; reduced transparency, increased contrast and reduced motion all have a tested path.
- Viewport FPS with panels open within 5% of today on the same machine.
- All existing e2e tests green; screenshots at three widths reviewed.

## 8. Owner decisions (2026-10-23)

1. Light only.
2. `/` stays the blank editor for now.
