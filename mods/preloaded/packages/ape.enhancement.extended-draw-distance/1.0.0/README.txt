Extended Draw Distance

This is an experimental, opt-in graphics enhancement. It enables the PSXRecomp
framework's guarded ordering-table depth clamp on ten traced main-EXE sites
where GTE SZ3 is shifted into a depth bucket before being stored.

Every site has an expected-instruction guard. The clamp bounds depth values
rather than raising the game's ordering-table limits, so far primitives can
land in the farthest safe bucket instead of being dropped. The feature is off
by default. If a scene looks wrong, disable it; this first pass does not remove
every independent game-side visibility or frustum test.
