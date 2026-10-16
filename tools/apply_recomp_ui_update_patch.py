#!/usr/bin/env python3
"""Apply the small Ape Escape-specific Nightly updater action to pinned recomp-ui.

The shared UI is a submodule and is intentionally not forked. This patch is
idempotently applied at CMake configure time, and only affects this project's
build. It adds a dashboard button which starts the bundled updater helper.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

SOURCE = Path("src/common/backends/imgui/launcher_imgui.cpp")
INCLUDE_ANCHOR = '#include "launcher_sdlcompat.h"   // pulls the right SDL header + event shim'
DRAW_ANCHOR = "void draw_dashboard(LauncherModel* m, const LauncherTheme& th, int logical_w) {"
END_ANCHOR = "\n}\n\n// Trim a path from the LEFT"
MARKER = "launch_nvd123_nightly_updater"

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
    char* base_raw = SDL_GetBasePath();
    if (!base_raw || !base_raw[0]) {
        if (base_raw) SDL_free(base_raw);
        if (error) *error = "Could not locate the installed application folder.";
        return false;
    }
    std::filesystem::path base = std::filesystem::path(base_raw).lexically_normal();
    SDL_free(base_raw);

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

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui-root", required=True, type=Path)
    parser.add_argument("--check", action="store_true",
                        help="fail unless the updater action is already patched")
    args = parser.parse_args()
    path = args.ui_root / SOURCE
    if not path.is_file():
        print(f"recomp-ui source not found: {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        if 'ImGui::Button("Check for Nightly Updates"' not in text:
            print("Updater helper exists but launcher button is missing.", file=sys.stderr)
            return 3
        print("recomp-ui updater action is already applied.")
        return 0
    if args.check:
        print("recomp-ui updater action has not been applied.", file=sys.stderr)
        return 1
    if text.count(INCLUDE_ANCHOR) != 1 or text.count(DRAW_ANCHOR) != 1 or text.count(END_ANCHOR) != 1:
        print("Pinned recomp-ui source no longer matches the guarded updater patch anchors.", file=sys.stderr)
        return 4

    text = text.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + "\n" + INCLUDES, 1)
    text = text.replace(DRAW_ANCHOR, HELPER + "\n" + DRAW_ANCHOR, 1)
    text = text.replace(END_ANCHOR, "\n" + BUTTON + END_ANCHOR, 1)
    path.write_text(text, encoding="utf-8")
    print(f"Applied nvd123 updater action to {path}.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
