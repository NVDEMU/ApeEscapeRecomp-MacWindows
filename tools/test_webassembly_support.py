#!/usr/bin/env python3
"""Static regression checks for the experimental Emscripten browser target."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools" / "apply_webassembly_runtime_patch.py"
SPEC = importlib.util.spec_from_file_location("web_patch", PATH)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("Could not load WebAssembly runtime patch")
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)

def check_runtime_patch():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        framework = base / "framework"
        (framework / "runtime" / "src").mkdir(parents=True)
        cmake = framework / "runtime" / "runtime.cmake"
        fiber = framework / "runtime" / "src" / "psx_fiber.c"
        gl = framework / "runtime" / "src" / "gpu_gl_renderer.c"
        main = framework / "runtime" / "src" / "main.cpp"
        cmake.write_text(PATCH.GL_START + "\n" + PATCH.OUTPUT_NAME_ANCHOR + "\n", encoding="utf-8")
        fiber.write_text('#include "psx_fiber.h"\n#if defined(_WIN32)\nvoid win(void) {}\n' +
                         PATCH.FIBER_ANCHOR + "\nvoid posix(void) {}\n#endif\n", encoding="utf-8")
        gl.write_text(PATCH.GL_DUMP_START + "\n", encoding="utf-8")
        main.write_text(PATCH.MAIN_INCLUDE_ANCHOR + "\n" + PATCH.MAIN_INIT_ANCHOR + "\n" + PATCH.VBLANK_PRESENT_ANCHOR + "\n", encoding="utf-8")
        project = base / "project"
        (project / "web").mkdir(parents=True)
        (project / "web" / "index.html").write_text("<html></html>", encoding="utf-8")
        (project / "web" / "wasm-pre.js").write_text("// pre-js\n", encoding="utf-8")
        (project / "game.toml").write_text('[runtime]\noverlay_cache = true\n[video]\nrenderer = "opengl"\ninternal_resolution = "4k"\nantialiasing = true\n', encoding="utf-8")
        build = base / "build"
        PATCH.apply(framework, project, build)
        first = (cmake.read_text(), fiber.read_text(), gl.read_text(), main.read_text())
        PATCH.apply(framework, project, build)
        if first != (cmake.read_text(), fiber.read_text(), gl.read_text(), main.read_text()):
            raise SystemExit("WebAssembly patch is not idempotent")
        if "APE_WEBASSEMBLY_GL_LINKAGE" not in first[0] or "createApeEscapeModule" not in first[0]:
            raise SystemExit("Browser OpenGL bypass or JS factory flags are missing")
        if "APE_WEBASSEMBLY_FIBERS" not in first[1] or "emscripten_fiber_swap" not in first[1]:
            raise SystemExit("Emscripten fiber backend is missing")
        if "getcontext(" in first[1].split(PATCH.FIBER_ANCHOR, 1)[0]:
            raise SystemExit("Emscripten fibers must precede POSIX ucontext")
        if "APE_WEBASSEMBLY_SKIP_GL_TEX_READBACK" not in first[2]:
            raise SystemExit("WebGL diagnostic readback stub is missing")
        if "APE_WEBASSEMBLY_SYNC_OVERLAY_INIT" not in first[3]:
            raise SystemExit("Emscripten overlay/cache initialization must not create a worker thread")
        if "#include <emscripten.h>" not in first[3] or "APE_WEBASSEMBLY_EVENT_LOOP_YIELD" not in first[3] or "emscripten_sleep(0)" not in first[3]:
            raise SystemExit("Emscripten browser runtime must yield to the event loop once per guest VBlank")
        staged = (build / "web-assets" / "game.toml").read_text(encoding="utf-8")
        for token in ('overlay_cache = true', 'renderer = "software"', 'internal_resolution = "native"', 'antialiasing = false'):
            if token not in staged:
                raise SystemExit(f"Browser config missing {token!r}")

def check_shell_workflow():
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    pre = (ROOT / "web" / "wasm-pre.js").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "webassembly.yml").read_text(encoding="utf-8")
    for token in ('accept=".chd,application/octet-stream"', 'createApeEscapeModule', 'ApeEscapeRecomp.js', "'--disc'", "/game/Ape Escape USA.chd"):
        if token not in page:
            raise SystemExit(f"Browser page missing {token!r}")
    for token in ("Module.preRun", "FS.writeFile", "apeEscapeDiscBytes", "/game/Ape Escape USA.chd"):
        if token not in pre:
            raise SystemExit(f"Browser pre-run hook missing {token!r}")
    for token in ("test_webassembly_support.py", "web-dist", "ApeEscapeRecomp.wasm"):
        if token not in workflow:
            raise SystemExit(f"WebAssembly workflow missing {token!r}")

if __name__ == "__main__":
    check_runtime_patch()
    check_shell_workflow()
    print("WebAssembly source-patch and browser-shell checks passed.")
