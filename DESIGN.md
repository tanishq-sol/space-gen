---
name: SpaceGen
description: Vellum over blueprint. A light, frosted interface laid over the scanned room, with navy ink and one drafted measurement signature.
colors:
  vellum: "#F5F7FA"
  paper: "#FFFFFF"
  ink: "#0B1F3A"
  navy: "#1B3A6B"
  slate: "#4D6080"
  muted: "#5E6F8A"
  hairline: "#DDE3EC"
  error: "#B42318"
typography:
  ui:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Text\", \"Segoe UI Variable\", system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
  ui-strong:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Text\", \"Segoe UI Variable\", system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.4
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"Segoe UI Variable Display\", system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.3
  display:
    fontFamily: "Hanken Grotesk, -apple-system, system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.01em"
  measurement:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Text\", \"Segoe UI Variable\", system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    fontFeature: "\"tnum\" 1"
rounded:
  control: "8px"
  panel: "14px"
  sheet: "18px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
components:
  button-primary:
    backgroundColor: "{colors.navy}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    height: "32px"
    padding: "0 14px"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    height: "32px"
    padding: "0 12px"
  panel-glass:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "12px"
  sheet-glass:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sheet}"
    padding: "12px 16px"
---

# Design System: SpaceGen

This file describes the NEW design system defined in `docs/design/ui-redesign-plan.md`. The system is not implemented in `frontend/` yet. The current UI is recorded only as the anti-reference at the end. Product truth lives in `PRODUCT.md`. A static direction mock is in `docs/design/mock/editor.html`, and its tokens are checked by `docs/design/mock/contrast.mjs`.

## Overview

**Creative North Star: "Vellum over blueprint."** SpaceGen's users work on a scanned room. Their two materials are the blueprint (navy ink, white linework, dimension lines) and drafting vellum or frosted architectural glass (a translucent sheet laid over a drawing so the drawing stays visible). The interface is a sheet of vellum laid over the scan: the room stays in charge, controls float on frosted panels above it, and the ink is navy.

**Key characteristics:**

- Light only. No dark theme ships in this redesign.
- The 3D scan is full bleed. Panels float over it and can collapse. Nothing boxes the scan in.
- Colour goes on data and on the single primary action in a view, never on chrome.
- Glass lives on the functional layer only, in two variants, with solid fallbacks.
- One memorable element, the measurement signature. Everything else stays quiet.
- Surfaces: Operate for the editor, Experience for the share page, Persuade for a future landing page (see PRODUCT.md). This file styles the first two; Persuade needs its own surface brief built from real product screens.

**Measured contrast** (script: `docs/design/mock/contrast.mjs`, WCAG 2.x):

| Pair | Ratio |
|---|---|
| ink on paper / on vellum | 16.52 / 15.39 |
| slate on vellum | 5.93 |
| muted on vellum / on paper | 4.75 / 5.10 |
| white on navy | 11.27 |
| error on paper | 6.57 |
| ink on regular glass (88% white over #202020) | 13.02 |
| slate on regular glass, worst case (88% white over #202020) | 5.02 |
| slate on regular glass over pure black | 4.84 |
| navy on regular glass over #202020 | 8.88 |
| ink on a selected row (navy 10% over that glass) | 11.03 |

## Colors

Restrained palette: white and navy with two blue-grey text steps. One accent (navy) used on under 10% of any view.

- **Vellum** (#F5F7FA): app ground, and the colour behind everything that is not the scan.
- **Paper** (#FFFFFF): opaque panels, sheets, the projects page cards, the glass base.
- **Ink** (#0B1F3A): primary text, icons, and the dimension lines of the measurement signature.
- **Navy** (#1B3A6B): the one primary action per view (white label, 11.27:1), selection outlines, the wordmark. Never a gradient, never a glow.
- **Slate** (#4D6080): secondary text. The only secondary text colour allowed on glass.
- **Muted** (#5E6F8A): hints and placeholders on opaque paper or vellum only. It fails on glass over dark pixels (4.02:1), so it is a forbidden pair there. The first pick #6B7C96 failed at 3.95:1 and was dropped.
- **Hairline** (#DDE3EC): borders and dividers. Decorative only (1.29:1 on paper), so it never carries meaning alone; selected and focused states use navy.
- **Error** (#B42318): errors only.

Derived tints, not new colours: selected row is navy at 10% over the surface; hover is ink at 5%; focus ring is navy at 2px offset 2px.

Dark values (reserved, not shipped): Night #0A1628, Deep #11223D, Frost #EEF2F8, Mist #A9B6CB, Sky #8FB0E8, error #F97066. They are for the walkthrough HUD over the scan and a possible later theme.

**The One Navy Rule.** At most one or two navy-filled controls per view, never a row of them. Navigation shows the active item as a neutral tint, not a coloured pill.

**The Muted-Not-On-Glass Rule.** On glass, text is ink or slate. Muted is for opaque surfaces.

## Typography

- **UI face:** the platform system stack (`-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI Variable", system-ui`). On a Mac this is Apple's type; on Windows the native equivalent. Replaces Inter.
- **Display face (projects header and share-page title only):** Hanken Grotesk 600, recommended after the comparison in `docs/design/mock/type-compare.html`. Not a serif, not Inter.
- **Numbers:** `font-variant-numeric: tabular-nums` on every measurement and count. Monospace only for real code or IDs, never for UI text.
- **Scale:** 11 / 13 / 15 / 17 / 22 / 28 px. App body 13 to 15, nothing below 11. Sentence case everywhere; no tracked uppercase labels.
- Roles: 11 meta and axis text; 13 UI and list rows; 15 panel body and inputs; 17 panel and project titles; 22 and 28 are display only, on the projects and share pages.

**The Numbers Rule.** Any figure that can change is tabular. Any figure that is a measurement is also in the measurement signature.

## Layout

Editor, regular (1280px and up): full-bleed scan; a glass toolbar floating 12px from the top edge; a glass Scene panel at left (296px) and Ask panel at right (332px), each 12px from the edges and collapsible; a glass tool palette centred at the bottom. Compact (under 1024px): panels become bottom sheets with a grabber; the toolbar keeps the project name, view mode and Share; everything else moves to a More menu. Scan content extends beneath the panels (Apple's "extend content beneath the sidebar").

Spacing runs on a 4px base: 4, 8, 12, 16. Panel inner padding 12. Hit targets are at least 28px on desktop and 44px on touch.

## Elevation & Depth

Two layers, following Apple's rule. **Content layer**: the scan, list rows, cards, the projects page. Flat, hairline or one tone step, no shadow, no glass. **Functional layer**: toolbar, tool palette, side panels, object action bar, walkthrough HUD, dialogs, popovers. Glass, and only glass.

| Variant | Recipe | Use |
|---|---|---|
| Regular | `backdrop-filter: blur(24px) saturate(1.4)`; fill white at 88%; 1px inner top highlight `rgba(255,255,255,.6)`; hairline border; shadow `0 8px 32px rgba(11,31,58,.12)` | Anything with text: panels, toolbar, dialogs |
| Clear | blur 12px; fill white 30%; a 35% dark dimming chip behind icons | Icon-only controls floating over the scan (walk HUD, view-mode switch). Never carries text |

Why 88% and not the plan's 85%: at 85% slate on glass over pure black is 4.50:1, with no margin. At 88% it is 4.84:1 over black and 5.02:1 over #202020. The plan's 85% is amended to 88%.

Fallbacks, all present in the mock CSS:

- `@supports not (backdrop-filter)` and `prefers-reduced-transparency: reduce`: opaque paper, no blur.
- `prefers-contrast: more`: solid paper, 1px ink-tinted border, no shadow.
- `prefers-reduced-motion: reduce`: all transitions and the sheet slide are off.
- At most about 4 glass surfaces on screen; glass over the WebGL canvas must not reduce viewport FPS (measured in phase 6).

**The Two-Layer Rule.** Never glass on a card, list row, the projects page or panel contents. Glass on glass is a defect: inside a glass panel, rows are flat with a hairline.

## Shapes

Radius by hierarchy, not one value: controls 8px, panels 14px, sheets and dialogs 18px. Pills only inside rows and beside a value, 20px tall at most. Icons are 16px outline (Lucide style), one set, ink or slate, no coloured containers.

## Components

- **Primary button:** navy fill, white 13px/600 label, 32px high, 8px radius, no shadow. One per view; in the editor it is Share.
- **Secondary button and segmented controls:** transparent or paper, ink label; the active segment is a white raised chip with a hairline (a neutral tint, not navy).
- **Toolbar:** regular glass, project name left, view mode centre, Share right. Orbit or Walk, Splat or Mesh or Both.
- **Tool palette:** regular glass, icon plus short label for select, wall, door, window, measure; active tool is a neutral tint with a navy 2px underline.
- **Scene panel:** regular glass; flat rows for objects, walls and layers; sentence-case section titles with counts; row selection is navy at 10%.
- **Ask panel:** regular glass; one AI proposal at a time with a ghost preview in the scan and one navy Apply button plus a quiet Dismiss; a variants row of small flat thumbnails.
- **Measurement signature** (the one memorable element): a drafted dimension line. A thin 1px ink line with 6px end ticks perpendicular to it, offset from the object; the label sits on the line on a small paper-glass chip: `≈ 2.10 m` in 13px/600 tabular figures, then `±2 cm` in slate 11px. It appears wherever sizes appear (object bar, drawings, walls, share page). The code string today is `≈ 2.35 m (±4 cm est.)` (`frontend/lib/measurement/accuracy.ts`); the signature splits it into the value and its error band, and keeps the word "est." in the tooltip.
- **Bottom sheet (compact):** sheet radius 18px, 36x5px grabber, regular glass, content scrolls inside.

## Do's and Don'ts

Do:

- Let the scan show through the panels; collapse panels to see more of it.
- Keep every measurement as `≈ value ±error`.
- Use plain verbs and sentence case: "Apply", "Share", "Ask about this object".
- Test every text pair over the darkest scan pixel behind it.

Don't:

- Use gradients, glows, or glass on content.
- Put the accent on chrome, tabs or navigation.
- Use uppercase tracked labels or monospace for UI text.
- Show internal names (Pascal, nodes, model ids) in copy.
- Use an icon in a coloured square, or a row of navy buttons.

## Anti-reference: the current UI

What the current dark UI does that reads as AI-made, with examples from the code (line numbers as of main at the start of this work). The redesign removes each.

| Tell | Examples |
|---|---|
| Indigo-to-violet brand gradient and gradient text | `frontend/tailwind.config.ts:52` `gradient-brand` (#6366F1 to #A855F7); `frontend/app/globals.css:32` `.text-gradient`; `frontend/components/layout/EditorLayout.tsx:54` "Space" + gradient "Gen"; `frontend/components/viewer/ObjectActionBar.tsx:102` and `ObjectReplacementModal.tsx:330` gradient buttons `from-accent to-purple-600` |
| Glow shadows | `frontend/tailwind.config.ts:45` `glow`; `frontend/app/globals.css:57` `.btn-primary` hover glow; `EditorLayout.tsx:50` logo `shadow-glow`; `tailwind.config.ts:66` `pulse-glow` animation |
| Near-black ground with one bright accent | `frontend/tailwind.config.ts:18` background `#06060C`; `frontend/app/layout.tsx:32` `themeColor: '#06060C'`; accent `#6366F1` at `tailwind.config.ts:31` |
| Uppercase tracked badges and labels | `frontend/app/globals.css:73` `.badge` (10px uppercase, tracking-wider); `frontend/components/AholoViewer/AholoViewerWorkspace.tsx:583` and 639, 726, 848 section labels `text-[11px] uppercase tracking-wider`; `frontend/components/capture/VideoCaptureModal.tsx:381` "Job" label |
| Monospace for ordinary UI text | `frontend/app/page.tsx:18` "Loading Pascal 3D workspace..." in `font-mono`; `AholoViewerWorkspace.tsx:614` a prompt textarea in `font-mono`; `frontend/app/splat-prototype/page.tsx:16` |
| Accent colour on chrome | 113 uses of `text-accent`, `bg-accent`, `border-accent` across `frontend/app` and `frontend/components` (counted with grep); the whole toolbar, tabs and selected states are indigo |
| Internal names in copy | `frontend/components/panels/ScenePanel.tsx:235` "{n} Pascal nodes registered"; `frontend/components/capture/ScanToEditableModal.tsx:105` "editable Pascal nodes"; `frontend/components/panels/ChatPanel.tsx:217` "Spatial AI Co-Pilot" with a Pascal and Gemini subtitle |
| Three fixed opaque columns box the scan in | `frontend/app/page.tsx:36` and `:49` (280px and 380px rails with `bg-surface`); the same widths at `frontend/app/editor/[projectId]/page.tsx:310` and `:321` |
| Default font | `frontend/app/layout.tsx:2` Inter plus JetBrains Mono |

Reference screenshots of the current UI: `docs/proposal-preview.png`, `docs/walkthrough-splat.png`, `docs/presentation.png`.

## Viewport imagery in the mock

`docs/design/mock/viewport.png` comes from `docs/presentation.png`, a real capture of the product's presentation view of the e2e fixture room (a splat scan with a detected chair proxy). It is the 1280x662 crop from y=56 to y=718, which drops the screenshot's caption pill, and the screenshot's "Items" card in the top right is retouched by linear interpolation of the pixels around it (that corner sits under the Ask panel). Nothing else is edited. A live capture from a running app was not made: the app build in a worktree needed a webpack build and a local backend, and that was stopped on instruction. The scan is soft because the splat is low resolution.
