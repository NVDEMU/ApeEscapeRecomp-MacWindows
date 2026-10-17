#!/usr/bin/env python3
"""Apply idempotent browser-only adaptations to the pinned PSXRecomp runtime."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

D = chr(36)
def cmake(text: str) -> str:
    return (text.replace("@TARGET@", D + "{target}")
                .replace("@GL_TARGET@", D + "{_psx_gl_target}")
                .replace("@EXE_NAME@", D + "{_psxrt_exe_name}")
                .replace("@SOURCE@", D + "{CMAKE_SOURCE_DIR}")
                .replace("@CURRENT_SOURCE@", D + "{CMAKE_CURRENT_SOURCE_DIR}")
                .replace("@BUILD@", D + "{CMAKE_BINARY_DIR}")
                .replace("@FRAMEWORK@", D + "{PSXRECOMP_ROOT}")
                .replace("@STATIC_C@", D + "{PSXRT_GAME_OVERLAY_STATIC_C}")
                .replace("@GAME_LINKED@", D + "{_ov_static_game_linked}")
                .replace("@OVERLAY_PROFILE@", D + "{_psxrt_overlay_profile}"))

GL_START = cmake("""        if(COMMAND recomp_resolve_gl)
            recomp_resolve_gl(_psx_gl_target)
            target_link_libraries(@TARGET@ PRIVATE @GL_TARGET@)
        else()
            # No recomp-ui checkout (PSX_RECOMP_UI=OFF): same resolution inline.
            find_package(OpenGL)
            if(TARGET OpenGL::GL)
                target_link_libraries(@TARGET@ PRIVATE OpenGL::GL)
            elseif(TARGET OpenGL::OpenGL)
                target_link_libraries(@TARGET@ PRIVATE OpenGL::OpenGL)
            elseif(OPENGL_gl_LIBRARY)
                target_link_libraries(@TARGET@ PRIVATE "@OPENGL_GL_LIB@")
            elseif(OPENGL_opengl_LIBRARY)
                target_link_libraries(@TARGET@ PRIVATE "@OPENGL_OPENGL_LIB@")
            endif()
        endif()""").replace("@OPENGL_GL_LIB@", D + "{OPENGL_gl_LIBRARY}").replace("@OPENGL_OPENGL_LIB@", D + "{OPENGL_opengl_LIBRARY}")

EMSCRIPTEN_GL = cmake("""        if(EMSCRIPTEN)
            # APE_WEBASSEMBLY_GL_LINKAGE: emcc supplies GLES/WebGL imports.
            # Do not search for native desktop OpenGL/GLX libraries in a browser build.
        elseif(COMMAND recomp_resolve_gl)
            recomp_resolve_gl(_psx_gl_target)
            target_link_libraries(@TARGET@ PRIVATE @GL_TARGET@)
        else()
            # No recomp-ui checkout (PSX_RECOMP_UI=OFF): same resolution inline.
            find_package(OpenGL)
            if(TARGET OpenGL::GL)
                target_link_libraries(@TARGET@ PRIVATE OpenGL::GL)
            elseif(TARGET OpenGL::OpenGL)
                target_link_libraries(@TARGET@ PRIVATE OpenGL::OpenGL)
            elseif(OPENGL_gl_LIBRARY)
                target_link_libraries(@TARGET@ PRIVATE "@OPENGL_GL_LIB@")
            elseif(OPENGL_opengl_LIBRARY)
                target_link_libraries(@TARGET@ PRIVATE "@OPENGL_OPENGL_LIB@")
            endif()
        endif()""").replace("@OPENGL_GL_LIB@", D + "{OPENGL_gl_LIBRARY}").replace("@OPENGL_OPENGL_LIB@", D + "{OPENGL_opengl_LIBRARY}")

OUTPUT_NAME_ANCHOR = cmake('    set_target_properties(@TARGET@ PROPERTIES OUTPUT_NAME "@EXE_NAME@")')
STATIC_OVERLAY_ANCHOR = cmake("""    psxrecomp_overlay_static_sources(_ov_static_sources _ov_static_present
        TARGET      "@TARGET@"
        STATIC_C    "@STATIC_C@"
        PROFILE     "@CURRENT_SOURCE@/aot/overlays.json"
        GAME_LINKED @GAME_LINKED@)""")
EMSCRIPTEN_STATIC_OVERLAY_BLOCK = cmake("""    if(EMSCRIPTEN)
        # APE_WEBASSEMBLY_STATIC_OVERLAY_PROFILE: use the parallel static-AOT profile.
        set(_psxrt_overlay_profile "@CURRENT_SOURCE@/aot/overlays-web.json")
    else()
        set(_psxrt_overlay_profile "@CURRENT_SOURCE@/aot/overlays.json")
    endif()
    psxrecomp_overlay_static_sources(_ov_static_sources _ov_static_present
        TARGET      "@TARGET@"
        STATIC_C    "@STATIC_C@"
        PROFILE     "@OVERLAY_PROFILE@"
        GAME_LINKED @GAME_LINKED@)""")
LINK_OPTIONS_ANCHOR = "# APE_WEBASSEMBLY_OUTPUT:"
EMSCRIPTEN_LINK_OPTIONS = cmake("""    # APE_WEBASSEMBLY_OUTPUT: JavaScript factory with preloaded runtime data.
    if(EMSCRIPTEN)
        target_compile_definitions(@TARGET@ PRIVATE APE_WEBASSEMBLY=1)
        target_link_options(@TARGET@ PRIVATE
            "-sUSE_WEBGL2=1"
            "-sMIN_WEBGL_VERSION=2"
            "-sMAX_WEBGL_VERSION=2"
            "-sMODULARIZE=1"
            "-sEXPORT_NAME=createApeEscapeModule"
            "-sASYNCIFY=1"
            "-sALLOW_MEMORY_GROWTH=1"
            "-sINITIAL_MEMORY=805306368"
            "-sMAXIMUM_MEMORY=3221225472"
            "-sSTACK_SIZE=67108864"
            "-sFORCE_FILESYSTEM=1"
            "-sASSERTIONS=1"
            "-sEXIT_RUNTIME=1"
            "-lidbfs.js"
            "SHELL:--pre-js @SOURCE@/web/wasm-pre.js"
            "SHELL:--preload-file @BUILD@/web-assets/game.toml@/game.toml"
            "SHELL:--preload-file @FRAMEWORK@/bios/openbios.bin@/bios/openbios.bin"
            "SHELL:--preload-file @FRAMEWORK@/bios/OpenBIOS.LICENSE@/bios/OpenBIOS.LICENSE"
            "SHELL:--preload-file @BUILD@/mods/bundled@/mods/bundled"
        )
    endif()""")

FIBER_ANCHOR = "#else /* POSIX: ucontext */"
EMSCRIPTEN_FIBER_BRANCH = r'''#elif defined(__EMSCRIPTEN__)
/* APE_WEBASSEMBLY_FIBERS
 * Use Emscripten's supported cooperative fiber API. Asyncify is enabled for
 * this target; the C stack and Asyncify stack must be separate allocations.
 */
#include <emscripten/fiber.h>
#include <stdint.h>
#include <stdlib.h>

#define PSX_FIBER_ASYNCIFY_STACK_SIZE (1024u * 1024u)

typedef struct psx_fiber_impl {
    emscripten_fiber_t ctx;
    void* stack;
    void* asyncify_stack;
    psx_fiber_entry entry;
    void* arg;
} psx_fiber_impl;

static psx_fiber_impl* s_current = NULL;

static void psx_fiber_emscripten_trampoline(void* opaque)
{
    psx_fiber_impl* f = (psx_fiber_impl*)opaque;
    f->entry(f->arg);
    /* Runtime fiber entries must switch back to the scheduler, not return. */
    abort();
}

psx_fiber_t psx_fiber_convert_thread(void)
{
    if (!s_current) {
        s_current = (psx_fiber_impl*)calloc(1, sizeof(*s_current));
        if (!s_current) abort();
        s_current->asyncify_stack = malloc(PSX_FIBER_ASYNCIFY_STACK_SIZE);
        if (!s_current->asyncify_stack) abort();
        emscripten_fiber_init_from_current_context(
            &s_current->ctx, s_current->asyncify_stack,
            PSX_FIBER_ASYNCIFY_STACK_SIZE);
    }
    return (psx_fiber_t)s_current;
}

psx_fiber_t psx_fiber_current(void)
{
    return (psx_fiber_t)s_current;
}

psx_fiber_t psx_fiber_create(size_t stack_size, psx_fiber_entry entry, void* arg)
{
    const size_t min_stack_size = 64u * 1024u;
    if (stack_size < min_stack_size) stack_size = min_stack_size;
    psx_fiber_impl* f = (psx_fiber_impl*)calloc(1, sizeof(*f));
    if (!f) return NULL;
    f->stack = malloc(stack_size);
    f->asyncify_stack = malloc(PSX_FIBER_ASYNCIFY_STACK_SIZE);
    if (!f->stack || !f->asyncify_stack) {
        free(f->stack);
        free(f->asyncify_stack);
        free(f);
        return NULL;
    }
    f->entry = entry;
    f->arg = arg;
    emscripten_fiber_init(&f->ctx, psx_fiber_emscripten_trampoline, f,
                          f->stack, stack_size, f->asyncify_stack,
                          PSX_FIBER_ASYNCIFY_STACK_SIZE);
    return (psx_fiber_t)f;
}

void psx_fiber_switch(psx_fiber_t target)
{
    psx_fiber_impl* to = (psx_fiber_impl*)target;
    psx_fiber_impl* from = s_current;
    if (!to || !from || to == from) return;
    s_current = to;
    emscripten_fiber_swap(&from->ctx, &to->ctx);
}

void psx_fiber_destroy(psx_fiber_t fiber)
{
    psx_fiber_impl* f = (psx_fiber_impl*)fiber;
    if (!f || f == s_current) return;
    free(f->stack);
    free(f->asyncify_stack);
    free(f);
}
#else /* POSIX: ucontext */'''

GL_DUMP_START = """static void pass_dump_generation(int gi) {
    PassGen *g = &s_pgen[gi];
    size_t n = (size_t)g->tex_w * (size_t)g->tex_h * 3u;
    uint8_t *rgb = (uint8_t *)malloc(n);
    if (!rgb) return;
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    for (uint32_t i = 0; i < g->n; i++) {
        char path[512];
        FILE *f;
        glBindTexture(GL_TEXTURE_2D, s_pgen_tex[gi][i]);
        glGetTexImage(GL_TEXTURE_2D, 0, GL_RGB, GL_UNSIGNED_BYTE, rgb);
        snprintf(path, sizeof path, "%s/g%03llu_%02u_a%05u.png", s_pdump_dir,
                 (unsigned long long)s_pdump_gen, (unsigned)i,
                 (unsigned)g->phase[i]);
        f = fopen(path, "wb");
        if (f) { (void)png_write_rgb(f, rgb, (uint32_t)g->tex_w, (uint32_t)g->tex_h); fclose(f); }
    }
    glBindTexture(GL_TEXTURE_2D, 0);
    free(rgb);
    s_pdump_gen++;
    s_pdump_left--;
}"""

EMSCRIPTEN_GL_DUMP = """#if defined(__EMSCRIPTEN__)
/* APE_WEBASSEMBLY_SKIP_GL_TEX_READBACK: WebGL has no glGetTexImage. This optional
 * diagnostic is disabled; ordinary rendering code remains available. */
static void pass_dump_generation(int gi) { (void)gi; }
#else
""" + GL_DUMP_START + """
#endif"""

def patch_runtime_cmake(text: str) -> str:
    if "# APE_WEBASSEMBLY_GL_LINKAGE:" not in text:
        if text.count(GL_START) != 1:
            raise ValueError("Expected one desktop OpenGL resolution block; refusing unsafe WebAssembly patch.")
        text = text.replace(GL_START, EMSCRIPTEN_GL, 1)
    if "# APE_WEBASSEMBLY_STATIC_OVERLAY_PROFILE:" not in text:
        if text.count(STATIC_OVERLAY_ANCHOR) != 1:
            raise ValueError("Expected one static-overlay profile selector; refusing unsafe WebAssembly AOT patch.")
        text = text.replace(STATIC_OVERLAY_ANCHOR, EMSCRIPTEN_STATIC_OVERLAY_BLOCK, 1)
    if LINK_OPTIONS_ANCHOR not in text:
        if text.count(OUTPUT_NAME_ANCHOR) != 1:
            raise ValueError("Expected one runtime OUTPUT_NAME anchor; refusing unsafe WebAssembly linker patch.")
        text = text.replace(OUTPUT_NAME_ANCHOR, OUTPUT_NAME_ANCHOR + "\n" + EMSCRIPTEN_LINK_OPTIONS, 1)
    return text

def patch_fiber(text: str) -> str:
    if "APE_WEBASSEMBLY_FIBERS" in text:
        return text
    if text.count(FIBER_ANCHOR) != 1:
        raise ValueError("Expected one POSIX ucontext fiber backend; refusing unsafe WebAssembly fiber patch.")
    return text.replace(FIBER_ANCHOR, EMSCRIPTEN_FIBER_BRANCH, 1)

def patch_gl_diagnostics(text: str) -> str:
    if "APE_WEBASSEMBLY_SKIP_GL_TEX_READBACK" in text:
        return text
    if text.count(GL_DUMP_START) != 1:
        raise ValueError("Expected one GPU pass-dump function; refusing unsafe WebGL compatibility patch.")
    return text.replace(GL_DUMP_START, EMSCRIPTEN_GL_DUMP, 1)

def stage_browser_assets(project_root: Path, build_root: Path) -> None:
    source = project_root / "game.toml"
    if not source.is_file():
        raise FileNotFoundError(f"Missing game config: {source}")
    content = source.read_text(encoding="utf-8")
    replacements = (
        ('renderer = "opengl"', 'renderer = "software"'),
        ('internal_resolution = "4k"', 'internal_resolution = "native"'),
        ("antialiasing = true", "antialiasing = false"),
    )
    for old, new in replacements:
        if content.count(old) != 1:
            raise ValueError(f"Expected exactly one browser config setting {old!r}, found {content.count(old)}")
        content = content.replace(old, new, 1)
    out = build_root / "web-assets" / "game.toml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    for relative in ("web/index.html", "web/wasm-pre.js"):
        if not (project_root / relative).is_file():
            raise FileNotFoundError(f"Missing browser port file: {project_root / relative}")

MAIN_INIT_ANCHOR = """    if (deferred_overlay_cache) {
        overlay_init_thread = std::thread([&]() {
            try {
                run_deferred_overlay_init();
            } catch (...) {
                overlay_init_exc = std::current_exception();
            }
        });
    }"""

MAIN_INIT_BROWSER = """    if (deferred_overlay_cache) {
#if defined(__EMSCRIPTEN__)
        /* APE_WEBASSEMBLY_SYNC_OVERLAY_INIT: Browser pthreads are not enabled.
         * Initialize the overlay/cache provider on the main thread instead.
         * No native overlay compiler is packaged; cache misses use interpreter fallback. */
        try {
            run_deferred_overlay_init();
        } catch (...) {
            overlay_init_exc = std::current_exception();
        }
#else
        overlay_init_thread = std::thread([&]() {
            try {
                run_deferred_overlay_init();
            } catch (...) {
                overlay_init_exc = std::current_exception();
            }
        });
#endif
    }"""

MAIN_INCLUDE_ANCHOR = '#include "spu_shadow.h"'
VBLANK_PRESENT_ANCHOR = """static void sdl_vblank_present(void) {
    sync_guest_cadence_to_video_standard();"""
VBLANK_PRESENT_BROWSER = """static void sdl_vblank_present(void) {
#if defined(__EMSCRIPTEN__)
    /* APE_WEBASSEMBLY_EVENT_LOOP_YIELD: this callback runs once per guest
     * VBlank inside the continuously running scheduler. Yield after the
     * previous frame was drawn so the browser can paint and process input. */
    emscripten_sleep(0);
#endif
    sync_guest_cadence_to_video_standard();"""

def patch_main(text: str) -> str:
    if "APE_WEBASSEMBLY_SYNC_OVERLAY_INIT" not in text:
        if text.count(MAIN_INIT_ANCHOR) != 1:
            raise ValueError("Expected one deferred overlay-init thread block in runtime/src/main.cpp; refusing unsafe browser thread patch.")
        text = text.replace(MAIN_INIT_ANCHOR, MAIN_INIT_BROWSER, 1)
    if "APE_WEBASSEMBLY_EVENT_LOOP_YIELD" not in text:
        if text.count(MAIN_INCLUDE_ANCHOR) != 1:
            raise ValueError("Expected one main.cpp include insertion anchor for Emscripten event-loop yielding.")
        if text.count(VBLANK_PRESENT_ANCHOR) != 1:
            raise ValueError("Expected one sdl_vblank_present anchor for Emscripten event-loop yielding.")
        text = text.replace(
            MAIN_INCLUDE_ANCHOR,
            MAIN_INCLUDE_ANCHOR + "\n#if defined(__EMSCRIPTEN__)\n#include <emscripten.h>\n#endif",
            1,
        )
        text = text.replace(VBLANK_PRESENT_ANCHOR, VBLANK_PRESENT_BROWSER, 1)
    return text

def apply(framework_root: Path, project_root: Path, build_root: Path) -> None:
    runtime_cmake = framework_root / "runtime" / "runtime.cmake"
    fiber_file = framework_root / "runtime" / "src" / "psx_fiber.c"
    gl_renderer = framework_root / "runtime" / "src" / "gpu_gl_renderer.c"
    runtime_main = framework_root / "runtime" / "src" / "main.cpp"
    for path in (runtime_cmake, fiber_file, gl_renderer, runtime_main):
        if not path.is_file():
            raise FileNotFoundError(f"Not the expected PSXRecomp checkout; missing {path}")
    cmake_text = runtime_cmake.read_text(encoding="utf-8-sig")
    fiber_text = fiber_file.read_text(encoding="utf-8-sig")
    gl_text = gl_renderer.read_text(encoding="utf-8-sig")
    main_text = runtime_main.read_text(encoding="utf-8-sig")
    runtime_cmake.write_text(patch_runtime_cmake(cmake_text), encoding="utf-8")
    fiber_file.write_text(patch_fiber(fiber_text), encoding="utf-8")
    gl_renderer.write_text(patch_gl_diagnostics(gl_text), encoding="utf-8")
    runtime_main.write_text(patch_main(main_text), encoding="utf-8")
    stage_browser_assets(project_root.resolve(), build_root.resolve())

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--build-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        apply(args.framework_root.resolve(), args.project_root.resolve(), args.build_root.resolve())
    except (OSError, ValueError) as exc:
        print(f"WebAssembly runtime patch failed: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
