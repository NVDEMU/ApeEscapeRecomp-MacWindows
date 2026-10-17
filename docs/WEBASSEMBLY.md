# Experimental WebAssembly port

This is an isolated browser target for Ape Escape Recompiled - Enhanced Edition on the experimental-webassembly branch. It does not modify master, desktop packages, the Android test APK or Nightly.

## Approach

The target uses Emscripten to compile the existing C/C++ runtime and generated game translation to WebAssembly. SDL is already the input/audio/window abstraction. The browser shell accepts a user-supplied USA .chd, writes it into Emscripten's virtual filesystem and launches the runtime. Commercial game data is not packaged or uploaded by this workflow.

If linking succeeds, the workflow produces ApeEscapeRecomp.js, ApeEscapeRecomp.wasm, ApeEscapeRecomp.data and index.html in the experimental artifact. Download all files together and serve from the same directory over HTTP. Opening index.html as a file URL is unsupported. A diagnostic log is uploaded even if compilation fails.

## Browser-specific adaptations

- Uses Emscripten's cooperative fiber API with Asyncify instead of Windows Fibers or POSIX ucontext.
- Skips native OpenGL/GLX package discovery; Emscripten supplies the GLES/WebGL imports.
- Disables the optional glGetTexImage renderer diagnostic, unsupported in WebGL. Normal rendering code remains available.
- Stages a browser-specific game config with overlay cache/autocompilation disabled, software rendering and native resolution. This avoids a native compiler dependency at startup; untranslated code falling back to the interpreter may be very slow.
- Preloads OpenBIOS, game config and the mod catalogue. The commercial CHD remains user-supplied.
- Attempts to store save files in IndexedDB through Emscripten's IDBFS backend, with diagnostics if persistence is unavailable.

## Current limitations and gates

This is an early port, not a claim of playable browser support. A successful configure or link does not prove game boot. Runtime overlay execution/autocompilation, SDL/browser event-loop behavior, graphics parity, sound, memory use and save durability still require real testing. The generated runtime has at least about 624 MB of static WebAssembly memory before loading the CHD, so this iteration sets an initial 768 MiB heap and allows growth to 3 GiB. The launcher also reads the full .chd into browser memory and copies it into the virtual filesystem; use a desktop browser with plenty of available RAM.

Milestones: (1) produce a complete .js/.wasm/.data bundle, (2) load the page and enter runtime without a startup abort, (3) reach the game, and (4) verify video, audio, controller input and saves. Only after those tests should this be considered for release distribution.

## Build workflow

Run Experimental WebAssembly feasibility on GitHub Actions, or push a change to this branch. The workflow runs regression checks before toolchain setup. Download ApeEscapeRecomp-WebAssembly-feasibility-log when the project build fails, or ApeEscapeRecomp-WebAssembly-Experimental when a complete bundle exists.
