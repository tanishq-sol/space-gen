# Product

<!-- impeccable:product-schema 1 -->

<!-- Provenance: written by a subagent with no human to interview. Facts come from README.md, docs/decisions/, docs/accuracy.md, docs/design/ui-redesign-plan.md and the frontend code. Items marked [inferred] are hypotheses to confirm with the owner. -->

## Platform

web

## Stack

Next.js (App Router) with React 19 and Tailwind 3 in `frontend/`; the 3D editor uses React Three Fiber, three.js and Gaussian splat renderers. FastAPI backend in `backend/`. The app has no accounts yet. Read `frontend/AGENTS.md` before touching frontend code: this Next.js version differs from older releases.

## Users

- **Architects and interior designers** who work from a scanned room. They open a capture, correct what the machine understood, try changes and show them to a client. [inferred from the capture-to-present pipeline in README.md and the share model in ADR 004]
- **Their clients**, who receive a share link, need no account, and can only look. They want to see the proposed space and compare options. (docs/decisions/004-sharing-and-auth.md)
- Today the designer side is a single trusted user on localhost; there is no sign-in.

## Product Purpose

Ellips turns a physical room into a persistent, conversationally editable digital twin: Capture, Reconstruct, Understand, Select, Ask, Generate, Validate, Explore, Compare, Present (README.md). A designer uploads a Gaussian-splat scan or a walkthrough video, gets walls, floor and openings as editable architecture and (with the GPU worker) furniture as movable objects, asks the AI for changes, previews each proposal as a ghost before applying it, keeps design variants, and presents the result.

Success is a designer who trusts what is on screen enough to quote it to a client, and a client who understands the proposal without a walkthrough from the designer.

## Positioning

The room stays the source of truth. Other tools start from an empty plan or a render; Ellips starts from the real scan, shows every size as an estimate with its error (`≈ 2.35 m (±4 cm est.)`), and lets AI propose changes in the room itself. The estimate and its error band are the product's honesty, and it must never be rounded into a false exact number (docs/accuracy.md).

## Operating Context

- Jobs per surface, with the mode each surface runs in:
  - **Editor** (`/editor/[projectId]`, and `/` as the blank editor): Operate. Inspect and correct the scan interpretation, select objects, edit walls, doors and windows, measure, ask the AI, apply or reject proposals, switch variants, produce drawings (plan and elevations).
  - **Import** (Convert Scan dialog, interpretation review): Operate. Upload a scan, watch conversion, review what was detected, and fix it before building the editable room.
  - **Projects** (`/projects`): Operate. Find a project and open it. A front door is planned.
  - **Walkthrough** (inside the editor): Experience. Move through the scan in first person.
  - **Share page** (`/p/[shareToken]`): Experience. A client looks at the scan, snapshots, viewpoints, variants and hero images, read-only, with measurements visible and product links.
  - **Presentation** (`/present`): Experience. A guided tour of a design.
  - **Landing page**: Persuade. Does not exist yet; planned after the product screens.
- Scans are large (hundreds of MB) and conversion is slow, so progress and errors are part of the daily workflow.
- The designer works at a desktop with a mouse; a client may open a share link on a phone. [inferred]

## Capabilities and Constraints

- The 3D viewport must stay fast. Chrome over the canvas must not cost frames; e2e tests measure splat FPS (`frontend/tests/e2e/splat-fps.spec.ts`) and the redesign targets within 5 percent of today.
- Measurements are always shown as `≈ X m ±Y cm`, never as bare exact numbers. The error comes from a table per scale source (`frontend/lib/measurement/errorTable.json`, currently synthetic placeholders). The current code string is `≈ 2.35 m (±4 cm est.)` (`frontend/lib/measurement/accuracy.ts`).
- Gaussian splats and meshes are shown together or separately (Splat, Mesh, Both) because the splat is the honest capture and the mesh is the editable one.
- AI proposals are previewed as ghosts and applied only on an explicit action; edits are undoable.
- Share links are bearer tokens, read-only, no-store and noindex (ADR 004). Client-facing screens must never expose editing controls or internal ids.
- No accounts, no dark theme. The light theme is the only theme in the redesign (owner decision, 2026-10-23).
- Terminology to use in the interface: scan, room, wall, door, window, object, proposal, variant, drawing. Internal names (Pascal, nodes, splat conversion jobs, model names) stay out of user-facing copy.
- Undecided: pricing, accounts, deployment, thumbnail rendering for the projects page (needs backend work).

## Brand Commitments

- Name: Ellips. Visual direction chosen by the owner: light only, white and navy, subtle, Apple-inspired, frosted Liquid Glass, and it must not look AI-made.
- Voice: plain verbs, sentence case, no filler, errors that say how to fix them. [inferred from the plan's Phase 4 clarify rules]
- No logo asset exists beyond the current text wordmark; the gradient mark is a placeholder to be replaced.

## Evidence on Hand

- Real product screenshots of the current dark UI in `docs/` (for example `docs/proposal-preview.png`, `docs/presentation.png`, `docs/variants-compare.png`) and the e2e fixture scan used by Playwright.
- A synthetic accuracy table only; no real-room accuracy data yet (docs/accuracy.md). Do not claim measured accuracy.
- No customers, testimonials, pricing or benchmarks exist. Do not invent any, including on a future landing page.

## Product Principles

1. The scan is in charge: controls float over it and never box it in.
2. Show uncertainty plainly: every size is an estimate with its error, in one consistent form.
3. Color goes on data and the one primary action in a view, not on chrome.
4. The designer stays in control: AI proposes, the designer applies.
5. The client surface is for looking: calm, light, nothing editable.

## Accessibility & Inclusion

- Every text pair at least 4.5:1 (3:1 for 18px and up), including text on glass over the darkest scan pixel.
- Reduced transparency, increased contrast and reduced motion each have a path; keyboard operation and visible focus in the editor; hit targets at least 28px on desktop and 44px on touch.
