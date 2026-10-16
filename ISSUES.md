# ApeEscapeRecomp — Issues

Current state (v0.0.2-alpha): Ape Escape **boots from the PS1 BIOS and plays** as
a native Windows program — through the intro, title, and gameplay, with dual-
analog controller input. It has not yet been verified all the way to the end, so
treat it as a very playable preview rather than a certified full playthrough.
**Memory-card save/load now works** (issue #4 fixed in v0.0.2) — progress saves
and loads back on standard `.mcd` images.

An **experimental 16:9 / 21:9 widescreen** mode is available in the launcher
(off by default). It uses Ape's stable GTE projection-and-stretch path for a
wider 3D field of view. Regular **4:3 is the accurate default** and is
unaffected.

---

## #1 — Widescreen: title sky "dome" doesn't reach the wide corners — FIXED

In widescreen, the **title and some menu screens** draw their sky as a
GTE-projected 3D dome mesh authored to fill a 4:3 frame. Its curved edge doesn't
reach the corners of the wider frame, so those corners show black. The 3D world,
gameplay skies, and cutscene skies all fill correctly — this is specific to the
finite sky-dome billboards on a few screens.

**Fixed** by identifying the title overlay's exact 16x16 sky-mesh projection
call (`0x8013660C`, return `0x80136614`). Only that producer bypasses the normal
widescreen X squash, preserving its authored 4:3 coverage for the final frame
stretch. The old depth-gated experiment is not used, so attract-demo geometry
is untouched.

---

## #2 — Widescreen: ferris-wheel cars cull at the 4:3 edge — FIXED

The ferris cabins remain submitted throughout the amusement-park shot on Ape's
original projection-and-stretch widescreen path. The unrelated native-wide
compositor and broad automatic/per-object cull experiments were removed from
the game config; those experiments caused severe attract-demo geometry wedges
without owning the cabin behavior.

---

## #3 — Widescreen: distance (draw-distance) pop-in at very wide FOV — OPEN

Separate from the edge culling above: the game stops drawing objects beyond a
fixed **distance** from the camera (a classic PS1 draw-distance / far-clip cull).
A wider field of view — especially at 21:9 — lets you see farther toward that
limit, so distant objects can be seen spawning in and out by *range* rather than
at the screen edge. This is a Z/distance cull, not an aspect-ratio one, so the
edge-cull widening doesn't touch it.

**Desired:** make the draw distance configurable (push it out so the player never
sees distant objects pop in/out, in whatever aspect they're playing). That means
tracing the game's distance-cull constant(s) and widening them behind a per-game
config knob (an opt-in, since a larger draw distance costs some performance and
changes the authored look). Same investigation shape as #1/#2 — deferred with
them.

**First opt-in pass (2026-10-15):** The new Extended Draw Distance mod clamps ten
traced GTE `SZ3` depth-bucket producer sites with expected-instruction guards.
It avoids raising the game's ordering-table bounds and remains disabled by
default. This targets far primitives dropped at the ordering-table depth limit;
it does **not** remove every separate game-side far-clip test, so this issue
stays open until the effect and any remaining pop-in are checked in gameplay.

---

## #4 — Memory-card save/load does not complete — FIXED (v0.0.2)

Reaching the memory-card screen to save or load progress did not complete. The
low-level card protocol worked on both this runtime and the Beetle oracle (card
reads succeed, an empty card reports empty, the SwCARD I/O-complete flag sets and
the card fhandler runs), so this was a **higher-layer timing race**, not a dead
card path. Two nondeterministic failure modes were seen: a soft stall on
"Checking… MEMORY CARD" (the interrupt-driven async card read aborted partway),
and, less often, a hard freeze from a register smear at the card-op consumer.

**Fixed** by a framework-level change to how a cooperative in-exception
thread-switch is *deferred* across interrupt delivery. The deferred switch is now
kept pending at dirty-interpreter pump sites (where a candidate resume PC is
committed but the live CPU state may not yet be materialized) and is not deferred
at all when the interrupted PC is in low BIOS/kernel space (which would otherwise
re-enter the same VBlank handler forever and starve the target thread). The switch
is honored only at a boundary where the resumed thread's CPU state is coherent, so
the card read/write completes cleanly. Class-level fix in the framework (no
per-game poke); validated on Ape Escape and regression-checked against MegaManX6
and Tomba (1).

---

## #5 — Widescreen: HUD / UI elements are stretched — FIXED

On the projection-and-stretch widescreen path, 3D geometry is squashed at GTE
projection time so the final frame stretch restores its proportions. Screen-space
2D elements (HUD, menu text, cursors) are **not** projected through the squashed
RTPS path, so the final stretch widens them: the HUD and UI render proportionally
stretched in 16:9 / 21:9. Reported during play validation of the v0.0.3-era
widescreen build.

**Investigated 2026-07-10 (GP0 ring + wtrace provenance, Fossil Field).**
- Ape's in-game HUD is mostly **polygons** (gouraud-textured quads/tris 0x3C/
  0x34/0x3E), not SPRT rects: cookie stack, gadget cross. Only the L2 chip and
  sparkle dots are SPRTs (0x65/0x67). The framework's untagged-SPRT
  `hud_sprt_squash` therefore cannot cover it, and untagged polys can't be
  blanket-squashed (the world is polys).
- Geometric proof of no-squash: gadget cross spans x 267..366 (flush right, a
  squash around centre would end it at ~341); cookie stack starts at x=7 (squash
  would put it at ~31). Both sit at authored 4:3 positions in the squashed frame.
- HUD packets are heap-allocated inline with world packets (single per-frame
  arena; addresses shift frame to frame; absolute submission order is
  interleaved), so neither packet address nor a flat command index is a stable
  classifier. The pause menu is the exception (dedicated static arena
  ~0xCA000-0xCBxxx, world not redrawn while paused).
- Producer map (wtrace writers → generated-C call graph):
  `func_8005BF70` (2588 B, jump-table-invoked, no static JAL callers) is the
  UI/HUD orchestrator. It calls the gadget-cross drawer `0x80043A8C` (dedicated,
  builder `0x80044EF4`), the L2-chip drawer `0x800691F8` (dedicated, SPRT-store
  leaf `0x8002B380`), and the HUD cookie-stack path `0x80063628 → 0x80017CD4 →
  0x800180B8`. Below `0x800180B8` the model-draw helpers (`0x8001B3CC`, the
  `0x8001A3xx` store loops) are **shared with world object rendering** — the
  HUD/world discrimination point is the orchestrator subtree, not the builders.

**Failed validation 2026-07-19.** Function-bracketing and packet-writer guesses
did not cover the title screen, the four-button gadget UI, or all character
draw paths. A 21:9 gameplay capture also showed squashed Spike and unacceptable
scene gaps. Those per-game hooks are disabled. The replacement must distinguish
GTE-projected geometry from screen-space UI at the submitted packet itself and
must pass paired 4:3 / 16:9 / 21:9 image checks before this issue is closed.

**Fixed 2026-07-27.** The framework now implements the `auto_ui_squash`
configuration already selected by Ape. Before a GPU DMA linked list is
executed, a read-only pass finds the highest ordering-table rank that actually
contains eligible textured UI. It groups adjacent glyphs/icons by texture and
screen row, computes the complete run bounds, and assigns one left/centre/right
anchor to every primitive in that run. The streamed GP0 commands are then
proportion-corrected around that shared anchor. This removes the old per-glyph
thirds decision that pulled the first and last letters of centred text in
opposite directions.

The classifier uses current-frame submission provenance rather than guest
function names, packet addresses, or one-frame-old geometry. Depth-sorted world
packets (including Spike) are below the selected UI layer, large backdrops are
excluded, and trailing empty ordering-table buckets no longer hide the real
front layer.

Validated on OpenGL with:

- 16:9 instruction text (`Capture 3 monkeys`), gameplay HUD, pause wheel, exit
  confirmation, and captured-monkey counter;
- 21:9 gameplay HUD and captured-monkey icons;
- the load/memory-card screen, which Ape's existing full-2D detector safely
  returns to 4:3 so its file names, percentages, and centred rows remain
  coherent; and
- widescreen disabled, where the 4:3 path reports identity squash and zero UI
  transforms.

The grouping math has a standalone regression test covering centred glyph
runs, right-edge icon runs, separated left/right runs, and dense menu anchoring.

---

## #6 — Widescreen: circus balls pop/cull during the rendered title sequence — OPEN

Near the beginning of the title/attract sequence, when Spike puts on his hat,
the circus balls can appear or disappear within the visible 21:9 frame. This is
not an FMV: it is a live rendered scene, and the original timing only guarantees
that these objects enter outside the 4:3 viewport.

**Investigation stopping point (2026-07-28):**

- The title overlay is loaded at `0x80136000`. Its event loop dispatches object
  record opcode `0x0F` through the handler at `0x80138404`, which ultimately
  submits the object through `0x800160EC`.
- The first identified circus-ball object is table index 16, object pointer
  `0x800BFAC0`. In an unmodified control run its first submission occurs at
  title-local frame 153 (host frame 1815). The exact 36-byte stream record was
  captured, so this path can be recognized again without repeating the broad
  search.
- A narrowly guarded experiment appended that record to queued title-stream
  blocks only for widescreen and only during title-local frames 120–152. It
  moved the first submission to frame 121, while the 4:3 control remained at
  frame 153.
- That experiment is **not accepted as a fix** and was removed. Moving the
  first submission earlier does not prove that the object follows the correct
  earlier trajectory or culling state, and the observed result was inconsistent:
  the latest run visibly culled the balls, while an earlier run appeared to
  handle their culling better.

Before resuming, compare the exact widescreen/culling configuration and build
state from the better-looking run against the latest run. Capture paired frames
around the hat animation and trace both ball objects, including their changing
transforms and visibility decisions. Do not treat an earlier static submission
by itself as closure.

---

## Audio / video regression status

The frame-smoothing guard was reviewed separately from the known widescreen issues. Phase value **3** is the active-gameplay phase used by the project’s gameplay plugins; the frame-replay hook had been rejecting that phase and therefore disabling interpolation during normal play. The guard now excludes transition/loading phases **4–6** but lets active gameplay reach its guarded capture/replay path. This is a source-level fix; verify smoothness, transition safety, and audio synchronization on actual hardware before declaring it glitch-free.

The remaining reproducible visual targets are documented above (#3 and #6). The broader regression checklist will track title/attract, FMVs, stage transitions, pause/resume, save/load, stock 4:3 and widescreen. No global audio engine setting or stock 4:3 rendering behavior was changed without a confirmed defect.

## Notes

- These are **enhancement-tier** items on the experimental widescreen path.
  4:3 is the authentic default and is byte-for-byte the original presentation.
- Widescreen is offered on both the OpenGL and Software renderers and was
  validated primarily on OpenGL (the shipping default).
