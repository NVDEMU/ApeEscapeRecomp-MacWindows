#!/usr/bin/env python3
"""Apply the Ape Escape brand theme/logo and updater action to pinned recomp-ui.

The shared UI remains a submodule. This idempotent project-local patch installs
our logo, selects a game-specific palette, and adds the repo-owned updater action.
"""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path
import sys

SOURCE = Path("src/common/backends/imgui/launcher_imgui.cpp")
INCLUDE_ANCHOR = '#include "launcher_sdlcompat.h"   // pulls the right SDL header + event shim'
DRAW_ANCHOR = "void draw_dashboard(LauncherModel* m, const LauncherTheme& th, int logical_w) {"
END_ANCHOR = "\n}\n\n// Trim a path from the LEFT"
MARKER = "launch_nvd123_nightly_updater"
THEME_HEADER = Path("src/common/launcher_theme.h")
PROFILE_HEADER = Path("src/consoles/psx/psx_profile.h")
LOGO_SOURCE = Path("recomp/launcher/ape_escape_logo.png")
LOGO_DEST = Path("assets/common/img/ape_escape_logo.png")
APE_THEME_MARKER = "launcher_theme_ape_escape"
APE_THEME_DISPATCH_MARKER = 'strcmp(name, "ape_escape")'
BRAND_SIZE_MARKER = "Ape Escape stacked-logo sizing"

APE_THEME = r'''// Ape Escape: saturated sky-blue panels, yellow primary actions and a clean
// no-scanline surface inspired by the original game's bright logo.
static inline LauncherTheme launcher_theme_ape_escape(void) {
    LauncherTheme t = launcher_theme_psx();
    t.background      = lng_rgba(0.016f, 0.063f, 0.184f, 1.0f); // #04102F
    t.background2     = lng_rgba(0.027f, 0.149f, 0.388f, 1.0f); // #072663
    t.panel           = lng_rgba(0.039f, 0.196f, 0.439f, 1.0f); // #0A3270
    t.panel_hovered   = lng_rgba(0.063f, 0.267f, 0.565f, 1.0f); // #104391
    t.control         = lng_rgba(0.047f, 0.161f, 0.365f, 1.0f); // #0C295D
    t.control_hovered = lng_rgba(0.086f, 0.302f, 0.635f, 1.0f); // #164DA2
    t.border          = lng_rgba(0.153f, 0.345f, 0.655f, 1.0f); // #2758A7
    t.accent          = lng_rgba(1.000f, 0.816f, 0.039f, 1.0f); // logo yellow
    t.accent_dim      = lng_rgba(0.902f, 0.667f, 0.000f, 1.0f); // pressed gold
    t.accent_text     = lng_rgba(0.020f, 0.090f, 0.247f, 1.0f); // dark-blue ink
    t.accent2         = lng_rgba(0.396f, 0.871f, 1.000f, 1.0f); // sky-blue headings
    t.text            = lng_rgba(0.984f, 0.992f, 1.000f, 1.0f);
    t.text_muted      = lng_rgba(0.725f, 0.816f, 0.969f, 1.0f);
    t.focus_ring      = lng_rgba(0.416f, 0.894f, 1.000f, 1.0f);
    t.scanline        = lng_rgba(0.0f, 0.0f, 0.0f, 0.0f);
    t.radius_sm       = 9.0f;
    t.radius_lg       = 20.0f;
    t.row_height      = 46.0f;
    t.focus_ring_width = 3.0f;
    t.scanlines       = 0;
    return t;
}
'''

INCLUDES = r'''#if defined(_WIN32)
  #ifndef WIN32_LEAN_AND_MEAN
    #define WIN32_LEAN_AND_MEAN
  #endif
  #ifndef NOMINMAX
    #define NOMINMAX
  #endif
  #include <windows.h>
#else
  #include <sys/types.h>
  #include <unistd.h>
#endif'''

HELPER = r'''
/* Ape Escape's repo-owned updater. Kept outside the shared launcher model:
 * the button starts a trusted, bundled helper that owns network/install work. */
static std::string s_nvd123_update_status;

static bool launch_nvd123_nightly_updater(std::string* error) {
    /* SDL3 returns a borrowed const char* here; unlike SDL2, this must not
     * be released with SDL_free(). Copy the path before leaving this block. */
    const char* base_raw = SDL_GetBasePath();
    if (!base_raw || !base_raw[0]) {
        if (error) *error = "Could not locate the installed application folder.";
        return false;
    }
    std::filesystem::path base = std::filesystem::path(base_raw).lexically_normal();

#if defined(_WIN32)
    const std::filesystem::path python = base / "overlay_toolchain" / "python" / "python.exe";
    const std::filesystem::path script = base / "update" / "updater.py";
#elif defined(__APPLE__)
    const std::filesystem::path resources = (base / "../Resources").lexically_normal();
    const std::filesystem::path python = resources / "overlay_toolchain" / "python" / "bin" / "python3";
    const std::filesystem::path script = resources / "update" / "updater.py";
#else
    const std::filesystem::path python = base / "overlay_toolchain" / "python" / "bin" / "python3";
    const std::filesystem::path script = base / "update" / "updater.py";
#endif
    if (!std::filesystem::is_regular_file(python) ||
        !std::filesystem::is_regular_file(script)) {
        if (error) *error = "The updater is missing from this installation. Download the latest Nightly manually.";
        return false;
    }

#if defined(_WIN32)
    const std::wstring python_w = python.wstring();
    const std::wstring script_w = script.wstring();
    const std::wstring base_w = base.wstring();
    std::wstring command = L"\"" + python_w + L"\" \"" + script_w +
        L"\" --install-root \"" + base_w + L"\" --parent-pid " +
        std::to_wstring(GetCurrentProcessId());
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    if (!CreateProcessW(nullptr, command.data(), nullptr, nullptr, FALSE,
                        DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
                        nullptr, base_w.c_str(), &startup, &process)) {
        if (error) *error = "Windows could not start the updater helper.";
        return false;
    }
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return true;
#else
    const std::string python_s = python.string();
    const std::string script_s = script.string();
    const std::string base_s = base.string();
    const std::string parent_pid = std::to_string(static_cast<long long>(getpid()));
    const pid_t child = fork();
    if (child < 0) {
        if (error) *error = "Could not start the updater helper.";
        return false;
    }
    if (child == 0) {
        (void)setsid();
        execl(python_s.c_str(), python_s.c_str(), script_s.c_str(),
              "--install-root", base_s.c_str(),
              "--parent-pid", parent_pid.c_str(),
              static_cast<char*>(nullptr));
        _exit(127);
    }
    return true;
#endif
}
'''

BUTTON = r'''
    /* This button is injected only in the Ape Escape build. The bundled helper
     * checks NVDEMU's macos-nightly release and installs only after this app exits. */
    ImGui::Spacing();
    ImGui::Separator();
    ImGui::TextColored(col(th.accent2), "nvd123 Nightly Updates");
    ImGui::TextWrapped("Check for the latest Windows or Mac Nightly from the official nvd123 repository.");
    if (ImGui::Button("Check for Nightly Updates", ImVec2(px(235), px(34)))) {
        std::string error;
        if (launch_nvd123_nightly_updater(&error)) {
            s_nvd123_update_status =
                "Updater opened. Follow its prompt; close Ape Escape when asked to install.";
        } else {
            s_nvd123_update_status = error;
        }
    }
    if (!s_nvd123_update_status.empty()) {
        ImGui::TextWrapped("%s", s_nvd123_update_status.c_str());
    }
'''

def fail(message: str, code: int = 4) -> int:
    print(message, file=sys.stderr)
    return code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui-root", required=True, type=Path)
    parser.add_argument("--project-root", type=Path, default=Path.cwd(),
                        help="Ape Escape repository root (defaults to the current directory)")
    parser.add_argument("--check", action="store_true",
                        help="fail unless the branding and updater patches are already applied")
    args = parser.parse_args()
    ui_root = args.ui_root
    project_root = args.project_root

    launcher_path = ui_root / SOURCE
    theme_path = ui_root / THEME_HEADER
    profile_path = ui_root / PROFILE_HEADER
    logo_source = project_root / LOGO_SOURCE
    logo_dest = ui_root / LOGO_DEST
    for required in (launcher_path, theme_path, profile_path, logo_source):
        if not required.is_file():
            return fail(f"Required Ape Escape launcher input is missing: {required}", 2)

    # Preserve the repo-owned Nightly updater integration.
    launcher_text = launcher_path.read_text(encoding="utf-8")
    if MARKER not in launcher_text:
        if args.check:
            return fail("recomp-ui updater action has not been applied.", 1)
        if (launcher_text.count(INCLUDE_ANCHOR) != 1 or
                launcher_text.count(DRAW_ANCHOR) != 1 or
                launcher_text.count(END_ANCHOR) != 1):
            return fail("Pinned recomp-ui source no longer matches the guarded updater patch anchors.")
        launcher_text = launcher_text.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + "\n" + INCLUDES, 1)
        launcher_text = launcher_text.replace(DRAW_ANCHOR, HELPER + "\n" + DRAW_ANCHOR, 1)
        launcher_text = launcher_text.replace(END_ANCHOR, "\n" + BUTTON + END_ANCHOR, 1)
    elif 'ImGui::Button("Check for Nightly Updates"' not in launcher_text:
        return fail("Updater helper exists but launcher button is missing.", 3)

    # Make the supplied stacked logo legible in the top-left header without
    # changing the sizing rules for other system marks.
    if BRAND_SIZE_MARKER not in launcher_text:
        if args.check:
            return fail("Ape Escape logo sizing has not been applied.", 1)
        old_size = "brand_h = 32.0f;"
        new_size = 'brand_h = 48.0f; // Ape Escape stacked-logo sizing'
        if launcher_text.count(old_size) != 1:
            return fail("Pinned launcher header no longer matches the guarded logo-sizing anchor.")
        launcher_text = launcher_text.replace(old_size, new_size, 1)
    elif "brand_h = 48.0f; // Ape Escape stacked-logo sizing" not in launcher_text:
        return fail("Ape Escape logo sizing marker exists but its value is missing.")

    # Add the project-specific palette and dispatch it by the theme name.
    theme_text = theme_path.read_text(encoding="utf-8")
    theme_changed = False
    if "#include <string.h>" not in theme_text:
        if args.check:
            return fail("Ape Escape theme string helper include has not been applied.", 1)
        guard = "#define LAUNCHER_NG_THEME_H\n"
        if theme_text.count(guard) != 1:
            return fail("Pinned launcher theme header no longer matches the guarded include anchor.")
        theme_text = theme_text.replace(guard, guard + "\n#include <string.h>\n", 1)
        theme_changed = True

    theme_anchor = "// Pick a built-in theme by name"
    if APE_THEME_MARKER not in theme_text:
        if args.check:
            return fail("Ape Escape launcher palette has not been applied.", 1)
        if theme_text.count(theme_anchor) != 1:
            return fail("Pinned launcher theme header no longer matches the guarded palette anchor.")
        theme_text = theme_text.replace(theme_anchor, APE_THEME + "\n" + theme_anchor, 1)
        theme_changed = True

    if APE_THEME_DISPATCH_MARKER not in theme_text:
        if args.check:
            return fail("Ape Escape theme name is not connected to the theme selector.", 1)
        selector = "static inline LauncherTheme launcher_theme_by_name(const char* name) {\n"
        dispatch = ('    if (name && (strcmp(name, "ape_escape") == 0 || '
                    'strcmp(name, "ape-escape") == 0))\n'
                    '        return launcher_theme_ape_escape();\n')
        if theme_text.count(selector) != 1:
            return fail("Pinned launcher theme selector no longer matches the guarded theme-name anchor.")
        theme_text = theme_text.replace(selector, selector + dispatch, 1)
        theme_changed = True

    if theme_changed:
        theme_path.write_text(theme_text, encoding="utf-8")

    # Point this one-game PSX profile at the new palette and supplied brand art.
    profile_text = profile_path.read_text(encoding="utf-8")
    profile_edits = (
        ('/* theme    */ "psx",', '/* theme    */ "ape_escape",'),
        ('gi->theme    = "psx";', 'gi->theme    = "ape_escape";'),
        ('/* brand             */ "brand_psx.tga",',
         '/* brand             */ "ape_escape_logo.png",'),
    )
    profile_changed = False
    for old, new in profile_edits:
        if new in profile_text:
            continue
        if args.check:
            return fail(f"Ape Escape PSX profile branding is incomplete: expected {new}", 1)
        if profile_text.count(old) != 1:
            return fail(f"Pinned PSX profile no longer matches the guarded branding anchor: {old}")
        profile_text = profile_text.replace(old, new, 1)
        profile_changed = True

    required_profile_tokens = ('/* theme    */ "ape_escape",',
                               'gi->theme    = "ape_escape";',
                               '/* brand             */ "ape_escape_logo.png",')
    if any(token not in profile_text for token in required_profile_tokens):
        return fail("Ape Escape PSX profile branding is incomplete.", 1)
    if profile_changed:
        profile_path.write_text(profile_text, encoding="utf-8")

    # The launcher package flattens common images into assets/img. Keep the
    # source logo in this repo and copy it into the pinned UI only while building.
    logo_dest.parent.mkdir(parents=True, exist_ok=True)
    same_logo = logo_dest.is_file() and logo_dest.read_bytes() == logo_source.read_bytes()
    if not same_logo:
        if args.check:
            return fail("Ape Escape logo asset has not been staged in recomp-ui.", 1)
        shutil.copyfile(logo_source, logo_dest)

    if args.check:
        print("Ape Escape theme, top-left logo and Nightly updater patches are present.")
    else:
        launcher_path.write_text(launcher_text, encoding="utf-8")
        print("Applied Ape Escape theme/logo and nvd123 Nightly updater patches.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
