#!/usr/bin/env python3
"""Fast static/unit checks for the experimental Android target."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = ROOT / "tools" / "apply_android_runtime_patch.py"
SPEC = importlib.util.spec_from_file_location("apply_android_runtime_patch", PATCH_PATH)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("could not load Android patch script")
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)

def check_patch_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as td:
        framework = Path(td)
        (framework / "runtime" / "src").mkdir(parents=True)
        cmake = framework / "runtime" / "runtime.cmake"
        main = framework / "runtime" / "src" / "main.cpp"
        gl_renderer = framework / "runtime" / "src" / "gpu_gl_renderer.c"
        cmake.write_text(PATCH.RUNTIME_START + "\n" + PATCH.SDL_STATIC_START + "\n" + PATCH.GL_START + "\n", encoding="utf-8")
        main.write_text(
            '#include "psx_sdl.h"\nint main(int argc, char** argv) {\n  return argc + (argv != nullptr);\n}\n',
            encoding="utf-8",
        )
        gl_renderer.write_text(PATCH.GL_DUMP_START + "\n", encoding="utf-8")
        PATCH.apply(framework)
        first_cmake = cmake.read_text(encoding="utf-8")
        first_main = main.read_text(encoding="utf-8")
        first_gl = gl_renderer.read_text(encoding="utf-8")
        PATCH.apply(framework)
        if cmake.read_text(encoding="utf-8") != first_cmake:
            raise SystemExit("runtime CMake Android patch is not idempotent")
        if main.read_text(encoding="utf-8") != first_main:
            raise SystemExit("runtime main Android patch is not idempotent")
        if gl_renderer.read_text(encoding="utf-8") != first_gl:
            raise SystemExit("GPU GL renderer Android patch is not idempotent")
        if "#if defined(__ANDROID__)\\n/* APE_ANDROID_SKIP_GL_TEX_READBACK:" not in first_gl:
            raise SystemExit("Android GLES must exclude unsupported glGetTexImage diagnostic code")
        if "add_library(${target} SHARED" not in first_cmake:
            raise SystemExit("Android runtime target is not a shared library")
        if "# APE_ANDROID_SDL_SHARED" not in first_cmake:
            raise SystemExit("Android SDL3 shared-library configuration is missing")
        if "# APE_ANDROID_GLES_LINKAGE" not in first_cmake:
            raise SystemExit("Android GLES/EGL linkage branch is missing")
        if "target_link_libraries(${target} PRIVATE GLESv3 EGL)" not in first_cmake:
            raise SystemExit("Android runtime must link GLESv2/EGL rather than desktop OpenGL")
        if "set(SDL_SHARED ON CACHE BOOL" not in first_cmake:
            raise SystemExit("Android must build SDL3 as the shared library loaded by SDLActivity")
        if "SDL_GetAndroidInternalStoragePath" not in first_main:
            raise SystemExit("Android app-private storage support is missing")
        if first_main.count("APE_ANDROID_SHARED_STORAGE_ROOT") != 1:
            raise SystemExit("Android storage marker should occur once")

def check_project_scaffolding() -> None:
    required = [
        ROOT / "android" / "settings.gradle",
        ROOT / "android" / "gradle.properties",
        ROOT / "android" / "app" / "build.gradle",
        ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml",
        ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "nvd123" / "apeescape" / "MainActivity.java",
        ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "nvd123" / "apeescape" / "GameActivity.java",
        ROOT / ".github" / "workflows" / "android.yml",
        ROOT / "docs" / "ANDROID.md",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing Android scaffolding: " + ", ".join(missing))
    activity = (ROOT / "android" / "app" / "src" / "main" / "java" /
                "com" / "nvd123" / "apeescape" / "GameActivity.java").read_text(encoding="utf-8")
    if 'return new String[] { "SDL3", "ApeEscapeRecomp" };' not in activity:
        raise SystemExit("Android SDLActivity library order is not configured")
    if '"--game"' not in activity or '"--disc"' not in activity:
        raise SystemExit("Android game launch does not supply config and disc paths")
    gradle = (ROOT / "android" / "app" / "build.gradle").read_text(encoding="utf-8")
    if "sdlResDir" in gradle or "res.srcDir(sdlResDir)" in gradle:
        raise SystemExit("SDL template resources must not be merged with the app's custom resources")
    if "java.srcDir(sdlJavaDir)" not in gradle:
        raise SystemExit("SDL Java activity/controller sources are not staged")
    workflow = (ROOT / ".github" / "workflows" / "android.yml").read_text(encoding="utf-8")
    for token in (
        "setup-android", "assembleDebug", "upload-artifact", "app-debug.apk",
        "download_disc.py", "chdman extractcd", "prepare_disc.py",
        "psxrecomp-game --config game.toml",
        "GAME_ASSETS_REPO: NVDEMU/apeescapeprivateassets",
        "GAME_ASSETS_FILENAME: Ape.Escape.USA.chd",
    ):
        if token not in workflow:
            raise SystemExit(f"Android workflow missing expected step: {token}")
    gradle = (ROOT / "android" / "app" / "build.gradle").read_text(encoding="utf-8")
    for token in ("psxrecomp-v4/bios/openbios.bin", "psxrecomp-v4/bios/OpenBIOS.LICENSE"):
        if token not in gradle:
            raise SystemExit(f"Android APK is missing bundled BIOS staging: {token}")

if __name__ == "__main__":
    check_patch_is_idempotent()
    check_project_scaffolding()
    print("Android patch and project checks passed.")
