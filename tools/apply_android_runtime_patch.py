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

def patch_runtime_cmake(text: str) -> str:
    if "# APE_ANDROID_SHARED_RUNTIME" in text:
        return text
    if text.count(RUNTIME_START) != 1:
        raise ValueError("Expected one known runtime add_executable() block in runtime/runtime.cmake; refusing an unsafe patch.")
    return text.replace(RUNTIME_START, ANDROID_RUNTIME, 1)

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
    if not runtime_cmake.is_file() or not main_cpp.is_file():
        raise FileNotFoundError(f"{framework_root} is not the expected PSXRecomp framework checkout")
    cmake_text = runtime_cmake.read_text(encoding="utf-8-sig")
    main_text = main_cpp.read_text(encoding="utf-8-sig")
    runtime_cmake.write_text(patch_runtime_cmake(cmake_text), encoding="utf-8")
    main_cpp.write_text(patch_main_cpp(main_text), encoding="utf-8")

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
