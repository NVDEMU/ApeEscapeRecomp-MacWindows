# Experimental WebAssembly port

This is an isolated browser target for Ape Escape Recompiled - Enhanced Edition on the experimental-webassembly branch. It does not modify master, desktop packages, the Android test APK or Nightly.

## Approach

The target uses Emscripten to compile the existing C/C++ runtime and generated game translation to WebAssembly. SDL is already the input/audio/window abstraction. The browser shell accepts a user-supplied USA .chd plus a matching user-dumped SCPH-1001 BIOS image (512 KiB), writes both into Emscripten's virtual filesystem and launches the runtime with that retail BIOS explicitly selected. The framework's MIT-licensed OpenBIOS image and license are also included because the runtime validates those default assets even when a retail BIOS is selected. OpenBIOS is distinct from, and not a substitute for, the selected 512 KiB retail BIOS. The commercial game image and retail BIOS are never packaged or uploaded.

If linking succeeds, the workflow produces ApeEscapeRecomp.js, ApeEscapeRecomp.wasm, ApeEscapeRecomp.data and index.html in the experimental artifact. Download all files together and serve from the same directory over HTTP. Opening index.html as a file URL is unsupported. A diagnostic log is uploaded even if compilation fails.

## Browser-specific adaptations

- Uses Emscripten's cooperative fiber API with Asyncify instead of Windows Fibers or POSIX ucontext.
- Skips native OpenGL/GLX package discovery; Emscripten supplies the GLES/WebGL imports.
- Disables the optional glGetTexImage renderer diagnostic, unsupported in WebGL. Normal rendering code remains available.
- Stages a browser-specific game config with overlay cache/autocompilation disabled, the OpenGL renderer backed by WebGL 2, native internal resolution and antialiasing off. A separate audited static AOT tier compiles the 16 verified mode-table overlays loaded at 0x80136000 before the browser executable is linked. This targets mode/cutscene transitions without compiling every overlay into the first browser build. Stage-specific area overlays (0x8013D000), the two minigame executables, and unresolved members remain on the interpreter fallback for now. Overlay/cache initialization runs synchronously on the browser main thread because this target does not enable pthreads. If the startup AOT stage fails, the workflow logs the failure and safely builds with the previous fallback.
- Preloads the game config, mod catalogue and the framework's redistributable OpenBIOS image plus its license. The launcher stages the user's matching SCPH-1001 BIOS at runtime and explicitly passes it with `--bios /bios/SCPH1001.BIN`; the retail BIOS is never embedded or uploaded.
- Attempts to store save files in IndexedDB through Emscripten's IDBFS backend, with diagnostics if persistence is unavailable.

## Current limitations and gates

This is an early port, not a claim of playable browser support. A successful configure or link does not prove game boot. Runtime overlay execution/autocompilation, SDL/browser event-loop behavior, graphics parity, sound, memory use and save durability still require real testing. The generated runtime has at least about 624 MB of static WebAssembly memory before loading the CHD, so this iteration sets an initial 768 MiB heap and allows growth to 3 GiB. The launcher also reads the full .chd into browser memory and copies it into the virtual filesystem; use a desktop browser with plenty of available RAM.

Milestones: (1) produce a complete .js/.wasm/.data bundle, (2) load the page and enter runtime without a startup abort, (3) compare intro/title performance with the 16-image startup AOT tier, (4) verify a stage before expanding coverage, and (5) verify video, audio, controller input and saves. A successful build is not a performance measurement; browser frame pacing still requires real gameplay testing.

## Build workflow

Run Experimental WebAssembly feasibility on GitHub Actions, or push a change to this branch. The workflow runs regression checks before toolchain setup. Download ApeEscapeRecomp-WebAssembly-feasibility-log when the project build fails, or ApeEscapeRecomp-WebAssembly-Experimental when a complete bundle exists.
