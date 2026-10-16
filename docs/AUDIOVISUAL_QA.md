# Audio / video regression checks

A source-level review has not established a universal audio/video defect in the stock 4:3 presentation. The renderer is reverse-engineered; avoid global timing or audio changes based only on a hunch.

## Known open visual defects

- **Very wide FOV draw-distance pop-in:** the experimental Extended Draw Distance mod targets some ordering-table depth-bucket drops. Separate game-side far-clip tests may still pop. It remains off by default.
- **Title/attract circus-ball popping on widescreen:** visibility and trajectory near Spike putting on his hat are not fully traced. The previous experiment to submit objects earlier was rejected because it did not prove correct motion/culling.

## Reproducible smoke-test matrix

1. Stock **4:3**, OpenGL, frame smoothing off: cold boot, title/attract, intro FMV, gameplay, pause/resume, death/retry, stage exit and memory-card load/save.
2. Audio continuity: music and effects during title-to-gameplay transitions, pause/resume, stage transitions, FMV start/stop, save/load screens, and return to Time Station.
3. Frame smoothing off/on on the same route. Inspect moving geometry, transitions/menu frames, audio timing, and frame pacing separately. Extra render passes must not advance guest gameplay or the audio timeline.
4. Widescreen 16:9 and 21:9: compare matched frames around the title hat animation, HUD/gadget wheel, near/far scenery, and stage transitions. Keep the stock 4:3 capture for comparison.
5. Save-state/rewind: test whether visual state, current stage, timer and audio resume consistently, repeating each case at least three times.

Compilation alone cannot establish that the game is glitch-free.