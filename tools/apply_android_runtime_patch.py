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
    if not runtime_cmake.is_file() or not main_cpp.is_file() or not gl_renderer.is_file():
        raise FileNotFoundError(f"{framework_root} is not the expected PSXRecomp framework checkout")
    cmake_text = runtime_cmake.read_text(encoding="utf-8-sig")
    main_text = main_cpp.read_text(encoding="utf-8-sig")
    gl_text = gl_renderer.read_text(encoding="utf-8-sig")
    runtime_cmake.write_text(patch_runtime_cmake(cmake_text), encoding="utf-8")
    main_cpp.write_text(patch_main_cpp(main_text), encoding="utf-8")
    if "#if defined(__ANDROID__)\n/* APE_ANDROID_SKIP_GL_TEX_READBACK:" not in gl_text:
        if gl_text.count(GL_DUMP_START) != 1:
            raise ValueError("Expected one known GPU GL pass-dump function; refusing unsafe Android GLES compatibility patch.")
        gl_text = gl_text.replace(GL_DUMP_START, ANDROID_GL_DUMP, 1)
        gl_renderer.write_text(gl_text, encoding="utf-8")

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
