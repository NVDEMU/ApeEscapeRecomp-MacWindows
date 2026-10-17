# Experimental WebAssembly port

This is a separate, experimental browser target for **Ape Escape Recompiled - Enhanced Edition**. It is not part of Nightly and does not change the desktop or Android release workflows.

## Why Emscripten is worth trying

Emscripten compiles C/C++ to WebAssembly and supplies browser integration. SDL supports browser input, audio, graphics and gamepads, so the project's SDL-based runtime is a promising starting point. This is a feasibility port, not yet a promise that the game is playable in a browser.

## Known porting risks to investigate

1. **Fibers / cooperative context switching.** The native runtime uses platform-specific fiber/context mechanisms. Browser builds need a supported WebAssembly strategy; native ucontext and Windows Fibers cannot simply be reused.
2. **Runtime overlays.** The current runtime can use a native compiler and load native overlay libraries. Browsers cannot execute arbitrary native shared libraries. We need to determine which overlays can be precompiled and what happens for cache misses.
3. **Graphics.** The OpenGL renderer may need an OpenGL ES/WebGL-compatible path, and any unsupported GL calls must be isolated.
4. **Main loop and storage.** SDL's browser main-loop model and a browser-persistent save/config filesystem need explicit integration.
5. **Game data.** The browser package must not include the commercial game image. The page should let the user choose their own supported image; browser file access and memory requirements need testing.

## First milestone

The Experimental WebAssembly feasibility workflow is intentionally isolated to this branch and manually runnable. It sets up Emscripten, prepares the same generated game sources as the other builds, attempts a real Emscripten CMake configure/build, and uploads its log even when the port attempt exposes an unsupported native dependency. A successful toolchain smoke test or CMake configure alone does not mean the game boots.

Next steps after the first build report: fix the earliest real compiler/configuration blocker, add a small browser launcher and game-file picker, then test boot and controller input before calling it playable.
