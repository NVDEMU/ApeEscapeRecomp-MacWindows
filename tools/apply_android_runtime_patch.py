#!/usr/bin/env python3
"""Apply small, idempotent Android-only adaptations to the pinned PSXRecomp runtime."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

RUNTIME_START = """    add_executable(${target}
        ${PSXRECOMP_RUNTIME_SOURCES}
        ${mode_source}
        ${generated_sources}
        ${PSXRT_EXTRAS_SOURCES}
    )"""

SDL_STATIC_START = """        set(SDL_SHARED OFF CACHE BOOL "Build SDL3 shared library" FORCE)
        set(SDL_STATIC ON CACHE BOOL "Build SDL3 static library" FORCE)"""

ANDROID_SDL_LINKAGE = """        # APE_ANDROID_SDL_SHARED: SDLActivity explicitly loads libSDL3.so.
        if(ANDROID)
            set(SDL_SHARED ON CACHE BOOL "Build SDL3 shared library" FORCE)
            set(SDL_STATIC OFF CACHE BOOL "Build SDL3 static library" FORCE)
        else()
            set(SDL_SHARED OFF CACHE BOOL "Build SDL3 shared library" FORCE)
            set(SDL_STATIC ON CACHE BOOL "Build SDL3 static library" FORCE)
        endif()"""

ANDROID_RUNTIME = """    # APE_ANDROID_SHARED_RUNTIME: SDLActivity loads a shared library, not an exe.
    if(ANDROID)
        add_library(${target} SHARED
            ${PSXRECOMP_RUNTIME_SOURCES}
            ${mode_source}
            ${generated_sources}
            ${PSXRT_EXTRAS_SOURCES}
        )
        # Android's SDLActivity loads the last entry in getLibraries().
        set_target_properties(${target} PROPERTIES OUTPUT_NAME "ApeEscapeRecomp")
    else()
        add_executable(${target}
            ${PSXRECOMP_RUNTIME_SOURCES}
            ${mode_source}
            ${generated_sources}
            ${PSXRT_EXTRAS_SOURCES}
        )
    endif()"""

MAIN_INCLUDE_ANCHOR = '#include "psx_sdl.h"'
ANDROID_INCLUDE = '''#include "psx_sdl.h"
#if defined(__ANDROID__)
#include <SDL3/SDL_system.h>
#endif'''
MAIN_ENTRY_ANCHOR = "int main(int argc, char** argv) {"
ANDROID_ENTRY = """int main(int argc, char** argv) {
#if defined(__ANDROID__)
    // A mobile app's working directory is not its installation folder.
    // Keep relative config, mods, settings and save paths in app-private storage.
    const char* ape_android_files_dir = SDL_GetAndroidInternalStoragePath();
    if (ape_android_files_dir && ape_android_files_dir[0] != '\\0') {
        std::error_code ape_android_cwd_error;
        (void)std::filesystem::current_path(ape_android_files_dir,
                                            ape_android_cwd_error);
    }
#endif"""

GL_START = "        if(COMMAND recomp_resolve_gl)\n            recomp_resolve_gl(_psx_gl_target)\n            target_link_libraries(${target} PRIVATE ${_psx_gl_target})\n        else()\n            # No recomp-ui checkout (PSX_RECOMP_UI=OFF): same resolution inline.\n            find_package(OpenGL)\n            if(TARGET OpenGL::GL)\n                target_link_libraries(${target} PRIVATE OpenGL::GL)\n            elseif(TARGET OpenGL::OpenGL)\n                target_link_libraries(${target} PRIVATE OpenGL::OpenGL)\n            elseif(OPENGL_gl_LIBRARY)\n                target_link_libraries(${target} PRIVATE \"${OPENGL_gl_LIBRARY}\")\n            elseif(OPENGL_opengl_LIBRARY)\n                target_link_libraries(${target} PRIVATE \"${OPENGL_opengl_LIBRARY}\")\n            endif()\n        endif()"

ANDROID_GL_LINKAGE = "        if(ANDROID)\n            # APE_ANDROID_GLES_LINKAGE: Android provides GLES/EGL, not desktop GLX/OpenGL.\n            target_link_libraries(${target} PRIVATE GLESv3 EGL)\n        elseif(COMMAND recomp_resolve_gl)\n            recomp_resolve_gl(_psx_gl_target)\n            target_link_libraries(${target} PRIVATE ${_psx_gl_target})\n        else()\n            # No recomp-ui checkout (PSX_RECOMP_UI=OFF): same resolution inline.\n            find_package(OpenGL)\n            if(TARGET OpenGL::GL)\n                target_link_libraries(${target} PRIVATE OpenGL::GL)\n            elseif(TARGET OpenGL::OpenGL)\n                target_link_libraries(${target} PRIVATE OpenGL::OpenGL)\n            elseif(OPENGL_gl_LIBRARY)\n                target_link_libraries(${target} PRIVATE \"${OPENGL_gl_LIBRARY}\")\n            elseif(OPENGL_opengl_LIBRARY)\n                target_link_libraries(${target} PRIVATE \"${OPENGL_opengl_LIBRARY}\")\n            endif()\n        endif()"

FIBER_ANCHOR = "#else /* POSIX: ucontext */"
ANDROID_FIBER_BRANCH = "#elif defined(__ANDROID__) && defined(__aarch64__)\n/* APE_ANDROID_AARCH64_FIBERS\n * Bionic does not expose getcontext/makecontext/swapcontext. This small\n * cooperative AArch64 context switch preserves the AAPCS64 callee-saved\n * integer/floating-point registers, stack pointer, FPCR, and FPSR. The game\n * scheduler is single-threaded and only switches at explicit fiber calls.\n */\n#include <stdint.h>\n#include <stdlib.h>\n\ntypedef struct psx_fiber_impl {\n    uint64_t callee_saved[12]; /* x19-x30 */\n    uintptr_t sp;\n    uint64_t fp_d8_d15[8];     /* d8-d15, AAPCS64 callee-saved FP registers */\n    uint64_t fpcr;\n    uint64_t fpsr;\n    void* stack;\n    psx_fiber_entry entry;\n    void* arg;\n} psx_fiber_impl;\n\nstatic psx_fiber_impl* s_current = NULL;\n\nvoid psx_fiber_android_switch(psx_fiber_impl* from, psx_fiber_impl* to);\n\n__asm__(\n    \".text\\n\"\n    \".align 2\\n\"\n    \".global psx_fiber_android_switch\\n\"\n    \".type psx_fiber_android_switch, %function\\n\"\n    \"psx_fiber_android_switch:\\n\"\n    \"stp x19, x20, [x0, #0]\\n\"\n    \"stp x21, x22, [x0, #16]\\n\"\n    \"stp x23, x24, [x0, #32]\\n\"\n    \"stp x25, x26, [x0, #48]\\n\"\n    \"stp x27, x28, [x0, #64]\\n\"\n    \"stp x29, x30, [x0, #80]\\n\"\n    \"mov x9, sp\\n\"\n    \"str x9, [x0, #96]\\n\"\n    \"stp d8, d9, [x0, #104]\\n\"\n    \"stp d10, d11, [x0, #120]\\n\"\n    \"stp d12, d13, [x0, #136]\\n\"\n    \"stp d14, d15, [x0, #152]\\n\"\n    \"mrs x9, fpcr\\n\"\n    \"str x9, [x0, #168]\\n\"\n    \"mrs x9, fpsr\\n\"\n    \"str x9, [x0, #176]\\n\"\n    \"ldp d8, d9, [x1, #104]\\n\"\n    \"ldp d10, d11, [x1, #120]\\n\"\n    \"ldp d12, d13, [x1, #136]\\n\"\n    \"ldp d14, d15, [x1, #152]\\n\"\n    \"ldr x9, [x1, #168]\\n\"\n    \"msr fpcr, x9\\n\"\n    \"ldr x9, [x1, #176]\\n\"\n    \"msr fpsr, x9\\n\"\n    \"ldr x9, [x1, #96]\\n\"\n    \"mov sp, x9\\n\"\n    \"ldp x19, x20, [x1, #0]\\n\"\n    \"ldp x21, x22, [x1, #16]\\n\"\n    \"ldp x23, x24, [x1, #32]\\n\"\n    \"ldp x25, x26, [x1, #48]\\n\"\n    \"ldp x27, x28, [x1, #64]\\n\"\n    \"ldp x29, x30, [x1, #80]\\n\"\n    \"mov x0, x19\\n\"\n    \"ret\\n\"\n    \".size psx_fiber_android_switch, .-psx_fiber_android_switch\\n\"\n);\n\nstatic void psx_fiber_android_trampoline(psx_fiber_impl* f)\n{\n    f->entry(f->arg);\n    /* Fiber entry points must switch away rather than return normally. */\n    abort();\n}\n\npsx_fiber_t psx_fiber_convert_thread(void)\n{\n    if (!s_current) {\n        s_current = (psx_fiber_impl*)calloc(1, sizeof(*s_current));\n    }\n    return (psx_fiber_t)s_current;\n}\n\npsx_fiber_t psx_fiber_current(void)\n{\n    return (psx_fiber_t)s_current;\n}\n\npsx_fiber_t psx_fiber_create(size_t stack_size, psx_fiber_entry entry, void* arg)\n{\n    const size_t min_stack_size = 64u * 1024u;\n    if (stack_size < min_stack_size) stack_size = min_stack_size;\n    psx_fiber_impl* f = (psx_fiber_impl*)calloc(1, sizeof(*f));\n    if (!f) return NULL;\n    f->stack = malloc(stack_size);\n    if (!f->stack) { free(f); return NULL; }\n    f->entry = entry;\n    f->arg = arg;\n    f->sp = ((uintptr_t)f->stack + stack_size) & ~(uintptr_t)0xFu;\n    f->callee_saved[0] = (uint64_t)(uintptr_t)f; /* x19: trampoline argument */\n    f->callee_saved[11] = (uint64_t)(uintptr_t)psx_fiber_android_trampoline; /* x30 */\n    return (psx_fiber_t)f;\n}\n\nvoid psx_fiber_switch(psx_fiber_t target)\n{\n    psx_fiber_impl* to = (psx_fiber_impl*)target;\n    psx_fiber_impl* from = s_current;\n    if (!to || !from || to == from) return;\n    s_current = to;\n    psx_fiber_android_switch(from, to);\n    /* On resume, s_current has been set by the fiber which switched here. */\n}\n\nvoid psx_fiber_destroy(psx_fiber_t fiber)\n{\n    psx_fiber_impl* f = (psx_fiber_impl*)fiber;\n    if (!f || f == s_current) return;\n    free(f->stack);\n    free(f);\n}\n#else /* POSIX: ucontext */"

GL_DUMP_START = "static void pass_dump_generation(int gi) {\n    PassGen *g = &s_pgen[gi];\n    size_t n = (size_t)g->tex_w * (size_t)g->tex_h * 3u;\n    uint8_t *rgb = (uint8_t *)malloc(n);\n    if (!rgb) return;\n    glPixelStorei(GL_PACK_ALIGNMENT, 1);\n    for (uint32_t i = 0; i < g->n; i++) {\n        char path[512];\n        FILE *f;\n        glBindTexture(GL_TEXTURE_2D, s_pgen_tex[gi][i]);\n        glGetTexImage(GL_TEXTURE_2D, 0, GL_RGB, GL_UNSIGNED_BYTE, rgb);\n        snprintf(path, sizeof path, \"%s/g%03llu_%02u_a%05u.png\", s_pdump_dir,\n                 (unsigned long long)s_pdump_gen, (unsigned)i,\n                 (unsigned)g->phase[i]);\n        f = fopen(path, \"wb\");\n        if (f) { (void)png_write_rgb(f, rgb, (uint32_t)g->tex_w, (uint32_t)g->tex_h); fclose(f); }\n    }\n    glBindTexture(GL_TEXTURE_2D, 0);\n    free(rgb);\n    s_pdump_gen++;\n    s_pdump_left--;\n}"

ANDROID_GL_DUMP = "#if defined(__ANDROID__)\n/* APE_ANDROID_SKIP_GL_TEX_READBACK: GLES has no glGetTexImage; pass dumps are\n * diagnostic tooling only and are disabled in the early Android target. */\nstatic void pass_dump_generation(int gi) { (void)gi; }\n#else\nstatic void pass_dump_generation(int gi) {\n    PassGen *g = &s_pgen[gi];\n    size_t n = (size_t)g->tex_w * (size_t)g->tex_h * 3u;\n    uint8_t *rgb = (uint8_t *)malloc(n);\n    if (!rgb) return;\n    glPixelStorei(GL_PACK_ALIGNMENT, 1);\n    for (uint32_t i = 0; i < g->n; i++) {\n        char path[512];\n        FILE *f;\n        glBindTexture(GL_TEXTURE_2D, s_pgen_tex[gi][i]);\n        glGetTexImage(GL_TEXTURE_2D, 0, GL_RGB, GL_UNSIGNED_BYTE, rgb);\n        snprintf(path, sizeof path, \"%s/g%03llu_%02u_a%05u.png\", s_pdump_dir,\n                 (unsigned long long)s_pdump_gen, (unsigned)i,\n                 (unsigned)g->phase[i]);\n        f = fopen(path, \"wb\");\n        if (f) { (void)png_write_rgb(f, rgb, (uint32_t)g->tex_w, (uint32_t)g->tex_h); fclose(f); }\n    }\n    glBindTexture(GL_TEXTURE_2D, 0);\n    free(rgb);\n    s_pdump_gen++;\n    s_pdump_left--;\n}\n#endif"

def patch_runtime_cmake(text: str) -> str:
    if "# APE_ANDROID_SHARED_RUNTIME" not in text:
        if text.count(RUNTIME_START) != 1:
            raise ValueError("Expected one known runtime add_executable() block in runtime/runtime.cmake; refusing an unsafe patch.")
        text = text.replace(RUNTIME_START, ANDROID_RUNTIME, 1)
    if "# APE_ANDROID_SDL_SHARED" not in text:
        if text.count(SDL_STATIC_START) != 1:
            raise ValueError("Expected one known SDL3 linkage block in runtime/runtime.cmake; refusing an unsafe patch.")
        text = text.replace(SDL_STATIC_START, ANDROID_SDL_LINKAGE, 1)
    if "# APE_ANDROID_GLES_LINKAGE" not in text:
        if text.count(GL_START) != 1:
            raise ValueError("Expected one known GL library resolution block in runtime/runtime.cmake; refusing an unsafe Android GL patch.")
        text = text.replace(GL_START, ANDROID_GL_LINKAGE, 1)
    return text

def patch_main_cpp(text: str) -> str:
    if "#include <SDL3/SDL_system.h>" not in text:
        if text.count(MAIN_INCLUDE_ANCHOR) != 1:
            raise ValueError("Expected one SDL include anchor in runtime/src/main.cpp.")
        text = text.replace(MAIN_INCLUDE_ANCHOR, ANDROID_INCLUDE, 1)
    if "APE_ANDROID_SHARED_STORAGE_ROOT" not in text:
        if text.count(MAIN_ENTRY_ANCHOR) != 1:
            raise ValueError("Expected one main() entry anchor in runtime/src/main.cpp.")
        android_entry = ANDROID_ENTRY.replace(
            MAIN_ENTRY_ANCHOR,
            MAIN_ENTRY_ANCHOR + "\n    // APE_ANDROID_SHARED_STORAGE_ROOT",
            1,
        )
        text = text.replace(MAIN_ENTRY_ANCHOR, android_entry, 1)
    return text

def apply(framework_root: Path) -> None:
    runtime_cmake = framework_root / "runtime" / "runtime.cmake"
    main_cpp = framework_root / "runtime" / "src" / "main.cpp"
    gl_renderer = framework_root / "runtime" / "src" / "gpu_gl_renderer.c"
    fiber_file = framework_root / "runtime" / "src" / "psx_fiber.c"
    if not runtime_cmake.is_file() or not main_cpp.is_file() or not gl_renderer.is_file() or not fiber_file.is_file():
        raise FileNotFoundError(f"{framework_root} is not the expected PSXRecomp framework checkout")
    cmake_text = runtime_cmake.read_text(encoding="utf-8-sig")
    main_text = main_cpp.read_text(encoding="utf-8-sig")
    gl_text = gl_renderer.read_text(encoding="utf-8-sig")
    fiber_text = fiber_file.read_text(encoding="utf-8-sig")
    runtime_cmake.write_text(patch_runtime_cmake(cmake_text), encoding="utf-8")
    main_cpp.write_text(patch_main_cpp(main_text), encoding="utf-8")
    if "#if defined(__ANDROID__)\n/* APE_ANDROID_SKIP_GL_TEX_READBACK:" not in gl_text:
        if gl_text.count(GL_DUMP_START) != 1:
            raise ValueError("Expected one known GPU GL pass-dump function; refusing unsafe Android GLES compatibility patch.")
        gl_text = gl_text.replace(GL_DUMP_START, ANDROID_GL_DUMP, 1)
        gl_renderer.write_text(gl_text, encoding="utf-8")
    fiber_marker = "APE_ANDROID_AARCH64_FIBERS"
    if fiber_marker not in fiber_text:
        if fiber_text.count(FIBER_ANCHOR) != 1:
            raise ValueError("Expected one known POSIX ucontext fiber backend; refusing unsafe Android fiber patch.")
        fiber_text = fiber_text.replace(FIBER_ANCHOR, ANDROID_FIBER_BRANCH, 1)
        fiber_file.write_text(fiber_text, encoding="utf-8")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        apply(args.framework_root.resolve())
    except (OSError, ValueError) as exc:
        print(f"Android runtime patch failed: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
