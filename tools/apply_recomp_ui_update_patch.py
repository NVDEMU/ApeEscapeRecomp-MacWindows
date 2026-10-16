#!/usr/bin/env python3
"""Apply the Ape Escape brand theme/logo and updater action to pinned recomp-ui.

The shared UI remains a submodule. This idempotent project-local patch installs
our logo, selects a game-specific palette, and adds the repo-owned updater action.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import struct
import zlib

SOURCE = Path("src/common/backends/imgui/launcher_imgui.cpp")
INCLUDE_ANCHOR = '#include "launcher_sdlcompat.h"   // pulls the right SDL header + event shim'
DRAW_ANCHOR = "void draw_dashboard(LauncherModel* m, const LauncherTheme& th, int logical_w) {"
END_ANCHOR = "\n}\n\n// Trim a path from the LEFT"
MARKER = "launch_nvd123_nightly_updater"
THEME_HEADER = Path("src/common/launcher_theme.h")
PROFILE_HEADER = Path("src/consoles/psx/psx_profile.h")
MODEL_HEADER = Path("src/common/launcher_model.h")
MONKEPEDIA_VIEW_MARKER = "APE_ESCAPE_MONKEPEDIA_VIEW"
LOGO_SOURCE = Path("recomp/launcher/ape_escape_logo.png")
LOGO_DEST = Path("assets/consoles/psx/img/brand_psx.tga")
APE_THEME_MARKER = "launcher_theme_ape_escape"
APE_THEME_DISPATCH_MARKER = 'strcmp(name, "ape_escape")'
BRAND_SIZE_MARKER = "Ape Escape stacked-logo sizing"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _paeth_predictor(left: int, up: int, upper_left: int) -> int:
    p = left + up - upper_left
    pa, pb, pc = abs(p - left), abs(p - up), abs(p - upper_left)
    if pa <= pb and pa <= pc:
        return left
    if pb <= pc:
        return up
    return upper_left


def png_to_tga(data: bytes) -> bytes:
    """Convert an 8-bit, non-interlaced PNG to a 32-bit alpha-preserving TGA.

    This deliberately uses only Python's standard library, so branding is
    generated consistently on Windows and macOS CI without external tools.
    PNG scanline filters and grayscale, RGB, indexed, grayscale-alpha, and
    RGBA inputs are supported.
    """
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("logo source is not a PNG file")

    width = height = bit_depth = color_type = interlace = None
    palette = transparency = None
    image_chunks = []
    offset = len(PNG_SIGNATURE)
    saw_end = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        offset += 8
        if offset + length + 4 > len(data):
            raise ValueError("logo PNG contains a truncated chunk")
        payload = data[offset:offset + length]
        offset += length + 4  # payload plus CRC
        if chunk_type == b"IHDR":
            if length != 13:
                raise ValueError("logo PNG has an invalid IHDR chunk")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if compression != 0 or filtering != 0:
                raise ValueError("logo PNG uses an unsupported compression or filter method")
        elif chunk_type == b"PLTE":
            palette = payload
        elif chunk_type == b"tRNS":
            transparency = payload
        elif chunk_type == b"IDAT":
            image_chunks.append(payload)
        elif chunk_type == b"IEND":
            saw_end = True
            break

    if not saw_end or width is None or height is None or not image_chunks:
        raise ValueError("logo PNG is missing required image data")
    if width < 1 or height < 1 or width > 65535 or height > 65535:
        raise ValueError("logo dimensions cannot be represented in a TGA file")
    if bit_depth != 8 or interlace != 0 or color_type not in (0, 2, 3, 4, 6):
        raise ValueError(
            "logo PNG must use 8-bit, non-interlaced grayscale, RGB, indexed, or RGBA pixels"
        )
    if color_type == 3 and (not palette or len(palette) % 3 != 0):
        raise ValueError("logo PNG has an invalid indexed-color palette")

    bytes_per_pixel = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    stride = width * bytes_per_pixel
    raw = zlib.decompress(b"".join(image_chunks))
    expected_size = height * (stride + 1)
    if len(raw) != expected_size:
        raise ValueError("logo PNG decompressed to an unexpected size")

    rows = []
    previous = bytearray(stride)
    pos = 0
    for _ in range(height):
        filter_type = raw[pos]
        scanline = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += stride + 1
        if filter_type == 1:  # Sub
            for i in range(stride):
                left = scanline[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                scanline[i] = (scanline[i] + left) & 0xFF
        elif filter_type == 2:  # Up
            for i in range(stride):
                scanline[i] = (scanline[i] + previous[i]) & 0xFF
        elif filter_type == 3:  # Average
            for i in range(stride):
                left = scanline[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                scanline[i] = (scanline[i] + ((left + previous[i]) // 2)) & 0xFF
        elif filter_type == 4:  # Paeth
            for i in range(stride):
                left = scanline[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                up = previous[i]
                upper_left = previous[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                scanline[i] = (
                    scanline[i] + _paeth_predictor(left, up, upper_left)
                ) & 0xFF
        elif filter_type != 0:
            raise ValueError(f"logo PNG uses unknown scanline filter {filter_type}")
        rows.append(scanline)
        previous = scanline

    pixels = bytearray(width * height * 4)
    out = 0
    for row in rows:
        for x in range(width):
            i = x * bytes_per_pixel
            if color_type == 6:  # RGBA
                red, green, blue, alpha = row[i:i + 4]
            elif color_type == 2:  # RGB
                red, green, blue = row[i:i + 3]
                alpha = 255
                if transparency and len(transparency) == 6:
                    tr, tg, tb = struct.unpack(">HHH", transparency)
                    if (red, green, blue) == (tr, tg, tb):
                        alpha = 0
            elif color_type == 4:  # grayscale + alpha
                red = green = blue = row[i]
                alpha = row[i + 1]
            elif color_type == 0:  # grayscale
                red = green = blue = row[i]
                alpha = 255
                if transparency and len(transparency) == 2:
                    transparent_gray = struct.unpack(">H", transparency)[0]
                    if red == transparent_gray:
                        alpha = 0
            else:  # indexed color
                index = row[i]
                palette_offset = index * 3
                if palette_offset + 3 > len(palette):
                    raise ValueError("logo PNG references a missing palette color")
                red, green, blue = palette[palette_offset:palette_offset + 3]
                alpha = transparency[index] if transparency and index < len(transparency) else 255
            pixels[out:out + 4] = bytes((blue, green, red, alpha))
            out += 4

    # TGA descriptor 0x28 means top-left origin and 8 bits of alpha.
    header = struct.pack(
        "<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0,
        width, height, 32, 0x28
    )
    return header + pixels


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

static bool launch_nvd123_nightly_updater(std::string* error, bool rollback = false) {
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
    if (rollback) command += L" --rollback";
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
        if (rollback) {
            execl(python_s.c_str(), python_s.c_str(), script_s.c_str(),
                  "--install-root", base_s.c_str(),
                  "--parent-pid", parent_pid.c_str(), "--rollback",
                  static_cast<char*>(nullptr));
        } else {
            execl(python_s.c_str(), python_s.c_str(), script_s.c_str(),
                  "--install-root", base_s.c_str(),
                  "--parent-pid", parent_pid.c_str(),
                  static_cast<char*>(nullptr));
        }
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
    const auto rollback_archive = ape_escape_data_directory() / "rollback" / "previous-build.zip";
    const bool rollback_available = std::filesystem::is_regular_file(rollback_archive);
    ImGui::Spacing();
    ImGui::TextDisabled("Rollback restores the last build saved by an in-app update.");
    if (!rollback_available) ImGui::BeginDisabled();
    if (ImGui::Button("Roll Back Last Build", ImVec2(px(235), px(34)))) {
        std::string error;
        if (launch_nvd123_nightly_updater(&error, true)) {
            s_nvd123_update_status = "Rollback started. Follow its prompt; close Ape Escape when asked.";
        } else {
            s_nvd123_update_status = error;
        }
    }
    if (!rollback_available) {
        ImGui::EndDisabled();
        ImGui::TextDisabled("A rollback becomes available after an in-app update has saved the previous build.");
    }
'''


# Accessibility / quality-of-life additions owned by this project. Keep these
# patches idempotent and fail closed if the pinned launcher changes underneath us.
PREFS_INCLUDE_MARKER = "APE_ESCAPE_LAUNCHER_PREFS_INCLUDE"
PREFS_MARKER = "ape_escape_accessibility_preferences"
ACCESSIBILITY_MARKER = "APE_ESCAPE_ACCESSIBILITY_SETTINGS"
QUICK_TOOLS_MARKER = "APE_ESCAPE_QUICK_TOOLS"
ACCESS_THEME_MARKER = "APE_ESCAPE_ACCESS_THEME_FRAME_LOOP"
DRAW_UI_ANCHOR = "void draw_ui(LauncherModel* m, const LauncherTheme& th, int logical_w, int logical_h) {"
SETTINGS_ANCHOR = '    if (hotkeys_p && !stacked_hotkeys) hotkeys_p->draw(m, &th);\n}'
RUNTIME_KEYBOARD = Path("psxrecomp-v4/runtime/src/psx_keybinds.c")
UI_KEYBOARD = Path("src/consoles/psx/psx_binds.c")
KEYBOARD_MARKER = "APE_ESCAPE_CUSTOM_KEYBOARD_DEFAULTS"

PREFS_STATE = r'''/* ape_escape_accessibility_preferences: per-user launcher-only preferences.
 * Stored beside the user's writable data so replacing the app never resets them. */
struct ApeEscapeLauncherPreferences {
    int text_percent = 100;
    bool high_contrast = false;
    bool large_controls = false;
    bool reduce_motion = false;
};
static ApeEscapeLauncherPreferences g_ape_escape_preferences;
static bool g_ape_escape_preferences_loaded = false;
static LauncherTheme g_ape_escape_accessible_theme{};
static std::string s_ape_escape_quick_status;

'''

PREFS_HELPER = r'''
static std::filesystem::path ape_escape_application_directory() {
    const char* base = SDL_GetBasePath();
    if (base && base[0]) return std::filesystem::path(base).lexically_normal();
    std::error_code ec;
    const auto cwd = std::filesystem::current_path(ec);
    return ec ? std::filesystem::path(".") : cwd;
}

static std::filesystem::path ape_escape_data_directory() {
    const char* override_dir = std::getenv("APE_ESCAPE_RECOMP_DATA_DIR");
    if (override_dir && override_dir[0])
        return std::filesystem::path(override_dir);
    /* SDL_GetPrefPath returns a writable, per-user path that survives replacing
     * an app bundle: Application Support on macOS, AppData on Windows, and the
     * platform's data directory on Linux. This is preferable to writing inside
     * a signed/read-only .app bundle. */
    char* pref_raw = SDL_GetPrefPath("NVDEMU", "Ape Escape Recompiled - Enhanced Edition");
    if (pref_raw && pref_raw[0]) {
        const std::filesystem::path pref(pref_raw);
        SDL_free(pref_raw);
        std::error_code ec;
        std::filesystem::create_directories(pref, ec);
        return pref;
    }
    if (pref_raw) SDL_free(pref_raw);
    return ape_escape_application_directory();
}

static std::filesystem::path ape_escape_preferences_path() {
    const auto path = ape_escape_data_directory() / "ape_escape_launcher.ini";
    std::error_code ec;
    if (!std::filesystem::exists(path, ec)) {
        const auto legacy = ape_escape_application_directory() / "ape_escape_launcher.ini";
        ec.clear();
        if (legacy != path && std::filesystem::is_regular_file(legacy, ec)) {
            ec.clear();
            std::filesystem::create_directories(path.parent_path(), ec);
            ec.clear();
            std::filesystem::copy_file(
                legacy, path, std::filesystem::copy_options::skip_existing, ec);
        }
    }
    return path;
}

static void ape_escape_load_preferences() {
    if (g_ape_escape_preferences_loaded) return;
    g_ape_escape_preferences_loaded = true;
    g_ape_escape_preferences = ApeEscapeLauncherPreferences{};
    std::ifstream in(ape_escape_preferences_path());
    std::string line;
    while (std::getline(in, line)) {
        const std::size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = line.substr(0, eq);
        const std::string value = line.substr(eq + 1);
        char* end = nullptr;
        const long parsed = std::strtol(value.c_str(), &end, 10);
        if (end == value.c_str() || *end != '\0') continue;
        if (key == "text_percent")
            g_ape_escape_preferences.text_percent =
                static_cast<int>(parsed < 80 ? 80 : parsed > 150 ? 150 : parsed);
        else if (key == "high_contrast")
            g_ape_escape_preferences.high_contrast = parsed != 0;
        else if (key == "large_controls")
            g_ape_escape_preferences.large_controls = parsed != 0;
        else if (key == "reduce_motion")
            g_ape_escape_preferences.reduce_motion = parsed != 0;
    }
}

static void ape_escape_save_preferences() {
    const auto path = ape_escape_preferences_path();
    std::error_code ec;
    std::filesystem::create_directories(path.parent_path(), ec);
    std::ofstream out(path, std::ios::trunc);
    if (!out) {
        s_ape_escape_quick_status = "Could not save launcher preferences.";
        return;
    }
    out << "# Ape Escape Recompiled launcher preferences; edited by the app.\n"
        << "text_percent=" << g_ape_escape_preferences.text_percent << "\n"
        << "high_contrast=" << (g_ape_escape_preferences.high_contrast ? 1 : 0) << "\n"
        << "large_controls=" << (g_ape_escape_preferences.large_controls ? 1 : 0) << "\n"
        << "reduce_motion=" << (g_ape_escape_preferences.reduce_motion ? 1 : 0) << "\n";
    if (!out) s_ape_escape_quick_status = "Could not finish saving launcher preferences.";
    else s_ape_escape_quick_status = "Launcher preferences saved.";
}

static void ape_escape_apply_accessibility_theme(LauncherTheme& theme) {
    if (g_ape_escape_preferences.high_contrast) {
        theme.background      = lng_rgba(0.0f, 0.0f, 0.0f, 1.0f);
        theme.background2     = lng_rgba(0.0f, 0.0f, 0.0f, 1.0f);
        theme.panel           = lng_rgba(0.015f, 0.015f, 0.045f, 1.0f);
        theme.panel_hovered   = lng_rgba(0.10f, 0.10f, 0.18f, 1.0f);
        theme.control         = lng_rgba(0.02f, 0.02f, 0.02f, 1.0f);
        theme.control_hovered = lng_rgba(0.15f, 0.15f, 0.20f, 1.0f);
        theme.border          = lng_rgba(1.0f, 1.0f, 1.0f, 1.0f);
        theme.accent          = lng_rgba(1.0f, 0.93f, 0.0f, 1.0f);
        theme.accent_dim      = lng_rgba(1.0f, 0.83f, 0.0f, 1.0f);
        theme.accent_text     = lng_rgba(0.0f, 0.0f, 0.0f, 1.0f);
        theme.accent2         = lng_rgba(0.50f, 0.90f, 1.0f, 1.0f);
        theme.text            = lng_rgba(1.0f, 1.0f, 1.0f, 1.0f);
        theme.text_muted      = lng_rgba(1.0f, 1.0f, 1.0f, 1.0f);
        theme.good            = lng_rgba(0.30f, 1.0f, 0.35f, 1.0f);
        theme.warn            = lng_rgba(1.0f, 0.85f, 0.0f, 1.0f);
        theme.focus_ring      = lng_rgba(0.50f, 0.95f, 1.0f, 1.0f);
        theme.focus_ring_width = 4.0f;
        theme.row_height       = 48.0f;
        theme.scanlines        = 0;
        theme.scanline         = lng_rgba(0.0f, 0.0f, 0.0f, 0.0f);
    }
    if (g_ape_escape_preferences.large_controls) {
        theme.row_height = 58.0f;
        theme.focus_ring_width = 4.0f;
    }
    if (g_ape_escape_preferences.reduce_motion) theme.scanlines = 0;
}

static void ape_escape_refresh_accessibility_theme(const LauncherTheme* base) {
    if (!base) return;
    ape_escape_load_preferences();
    g_ape_escape_accessible_theme = *base;
    ape_escape_apply_accessibility_theme(g_ape_escape_accessible_theme);
    g_th = &g_ape_escape_accessible_theme;
    ImGui::GetIO().FontGlobalScale =
        static_cast<float>(g_ape_escape_preferences.text_percent) / 100.0f;
}

static std::string ape_escape_file_url(const std::filesystem::path& path) {
    std::error_code ec;
    std::string raw = std::filesystem::absolute(path, ec).generic_string();
    if (ec) raw = path.generic_string();
    std::string url = "file://";
#if defined(_WIN32)
    url += "/";
#endif
    static const char kHex[] = "0123456789ABCDEF";
    for (unsigned char ch : raw) {
        if ((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') ||
            (ch >= '0' && ch <= '9') || ch == '/' || ch == ':' ||
            ch == '-' || ch == '_' || ch == '.' || ch == '~') {
            url.push_back(static_cast<char>(ch));
        } else {
            url.push_back('%');
            url.push_back(kHex[ch >> 4]);
            url.push_back(kHex[ch & 15]);
        }
    }
    return url;
}

static bool ape_escape_open_url(const std::string& url) {
#if defined(LNG_SDL3)
    const bool ok = SDL_OpenURL(url.c_str());
#else
    const bool ok = SDL_OpenURL(url.c_str()) == 0;
#endif
    if (!ok) s_ape_escape_quick_status = "Could not open the requested location.";
    return ok;
}

static bool ape_escape_open_folder(const std::filesystem::path& folder) {
    std::error_code ec;
    std::filesystem::create_directories(folder, ec);
    if (ec) {
        s_ape_escape_quick_status = "Could not access folder: " + folder.string();
        return false;
    }
    const bool ok = ape_escape_open_url(ape_escape_file_url(folder));
    if (ok) s_ape_escape_quick_status = "Opened folder: " + folder.string();
    return ok;
}

static bool ape_escape_open_disc_folder(const LauncherModel* m) {
    if (!m || !m->rom_present || !m->rom_full[0]) {
        s_ape_escape_quick_status = "Choose a disc first to open its folder.";
        return false;
    }
    std::filesystem::path disc(m->rom_full);
    const auto parent = disc.parent_path();
    if (parent.empty()) {
        s_ape_escape_quick_status = "The selected disc path has no parent folder.";
        return false;
    }
    return ape_escape_open_folder(parent);
}

static bool ape_escape_open_nightly_page() {
    return ape_escape_open_url(
        "https://github.com/NVDEMU/ApeEscapeRecomp-MacWindows/releases/tag/macos-nightly");
}

static std::string ape_escape_json_string(const std::string& json, const char* key) {
    const std::string needle = std::string("\"") + key + "\"";
    const std::size_t key_pos = json.find(needle);
    if (key_pos == std::string::npos) return {};
    const std::size_t colon = json.find(':', key_pos + needle.size());
    if (colon == std::string::npos) return {};
    const std::size_t quote = json.find('"', colon + 1);
    if (quote == std::string::npos) return {};
    std::string value;
    bool escaped = false;
    for (std::size_t i = quote + 1; i < json.size(); ++i) {
        const char ch = json[i];
        if (escaped) {
            value.push_back(ch);
            escaped = false;
        } else if (ch == '\\') {
            escaped = true;
        } else if (ch == '"') {
            return value;
        } else {
            value.push_back(ch);
        }
    }
    return {};
}

static std::string ape_escape_build_info() {
    const auto base = ape_escape_application_directory();
#if defined(__APPLE__)
    const auto provenance_path = (base / "../Resources/BUILD_PROVENANCE.json").lexically_normal();
#else
    const auto provenance_path = base / "BUILD_PROVENANCE.json";
#endif
    std::ifstream in(provenance_path);
    if (!in) return "Installed build: metadata unavailable";
    std::string json, line;
    while (std::getline(in, line)) { json += line; json += '\n'; }
    const std::string version = ape_escape_json_string(json, "version");
    const std::string channel = ape_escape_json_string(json, "channel");
    const std::string commit = ape_escape_json_string(json, "commit");
    std::string label = "Installed build: ";
    label += channel.empty() ? "unknown channel" : channel;
    if (!version.empty()) label += " v" + version;
    if (!commit.empty() && commit != "unknown")
        label += " | commit " + commit.substr(0, commit.size() < 12 ? commit.size() : 12);
    return label;
}

static void ape_escape_draw_accessibility_settings(const LauncherTheme& th) {
    // APE_ESCAPE_ACCESSIBILITY_SETTINGS
    ImGui::Spacing();
    ImGui::Separator();
    ImGui::TextColored(col(th.accent2), "ACCESSIBILITY");
    ImGui::TextWrapped(
        "Launcher-wide preferences. Changes save automatically and do not enable gameplay mods.");
    int text_percent = g_ape_escape_preferences.text_percent;
    ImGui::SetNextItemWidth(px(280.0f));
    if (ImGui::SliderInt("Launcher text size", &text_percent, 80, 150, "%d%%")) {
        g_ape_escape_preferences.text_percent = text_percent;
        ape_escape_save_preferences();
    }
    bool high_contrast = g_ape_escape_preferences.high_contrast;
    if (ImGui::Checkbox("High-contrast colors", &high_contrast)) {
        g_ape_escape_preferences.high_contrast = high_contrast;
        ape_escape_save_preferences();
    }
    bool large_controls = g_ape_escape_preferences.large_controls;
    if (ImGui::Checkbox("Larger controls and focus targets", &large_controls)) {
        g_ape_escape_preferences.large_controls = large_controls;
        ape_escape_save_preferences();
    }
    bool reduce_motion = g_ape_escape_preferences.reduce_motion;
    if (ImGui::Checkbox("Reduce visual effects", &reduce_motion)) {
        g_ape_escape_preferences.reduce_motion = reduce_motion;
        ape_escape_save_preferences();
    }
    if (ImGui::Button("Reset accessibility settings", ImVec2(px(230.0f), px(32.0f)))) {
        g_ape_escape_preferences.text_percent = 100;
        g_ape_escape_preferences.high_contrast = false;
        g_ape_escape_preferences.large_controls = false;
        g_ape_escape_preferences.reduce_motion = false;
        ape_escape_save_preferences();
    }
    ImGui::TextDisabled("These preferences are stored in ape_escape_launcher.ini.");
}
'''

ACCESSIBILITY_INSERT = r'''
    // APE_ESCAPE_SETTINGS_CARD
    ape_escape_draw_accessibility_settings(th);
'''

MONKEPEDIA_HELPER = r'''/* APE_ESCAPE_MONKEPEDIA_HELPER: local-only Monkey Book and play history. */
struct ApeMonkeEntry { int stage; int index; int monkey_level; std::string stage_name, name, description, source_url; };
struct ApeMonkeStage { int id; std::string name; int entries; };
struct ApeRunRecord {
    int stage = -1; std::int64_t timestamp = 0; unsigned frames = 0;
    unsigned caught = 0, triangles = 0, coins = 0, lives = 0; std::uint32_t mask = 0;
};
static std::vector<ApeMonkeEntry> s_ape_monke_entries;
static std::vector<ApeMonkeStage> s_ape_monke_stages;
static std::vector<ApeRunRecord> s_ape_run_history;
static std::unordered_map<int, std::uint32_t> s_ape_ever_caught;
static std::unordered_map<int, ApeRunRecord> s_ape_stage_bests;
static bool s_ape_monke_catalog_loaded = false, s_ape_run_history_loaded = false;
static int s_ape_monke_page = 0, s_ape_monke_stage = 0, s_ape_monke_entry = 1;
static char s_ape_monke_search[96] = "";

static std::vector<std::string> ape_escape_tsv_columns(const std::string& line) {
    std::vector<std::string> out; std::stringstream input(line); std::string part;
    while (std::getline(input, part, '\t')) out.push_back(part);
    if (!line.empty() && line.back() == '\t') out.emplace_back();
    return out;
}
static long ape_escape_monke_number(const std::string& value, int base = 10) {
    char* end = nullptr; const long n = std::strtol(value.c_str(), &end, base);
    return end == value.c_str() || *end ? 0L : n;
}
static const ApeMonkeStage* ape_escape_monke_stage(int id) {
    for (const auto& stage : s_ape_monke_stages) if (stage.id == id) return &stage;
    return nullptr;
}
static std::string ape_escape_monke_stage_name(int id) {
    const auto* s = ape_escape_monke_stage(id);
    return s ? s->name : ("Unmapped stage " + std::to_string(id));
}
static unsigned ape_escape_mask_count(std::uint32_t bits) {
    unsigned n = 0; while (bits) { n += bits & 1u; bits >>= 1u; } return n;
}
static std::string ape_escape_time_string(unsigned frames) {
    const unsigned ms = static_cast<unsigned>((static_cast<unsigned long long>(frames) * 1000ull) / 60ull);
    char out[32]; std::snprintf(out, sizeof(out), "%02u:%02u.%03u", ms / 60000u, (ms / 1000u) % 60u, ms % 1000u);
    return out;
}
static std::string ape_escape_date_string(std::int64_t timestamp) {
    if (timestamp <= 0) return "Unknown date";
    const std::time_t t = static_cast<std::time_t>(timestamp); std::tm local{};
#if defined(_WIN32)
    if (localtime_s(&local, &t) != 0) return "Unknown date";
#else
    if (!localtime_r(&t, &local)) return "Unknown date";
#endif
    char out[48]; return std::strftime(out, sizeof(out), "%Y-%m-%d %H:%M", &local) ? out : "Unknown date";
}
static void ape_escape_load_monke_catalog() {
    if (s_ape_monke_catalog_loaded) return;
    s_ape_monke_catalog_loaded = true;
    std::ifstream in(ape_escape_application_directory() / "assets" / "monkepedia.tsv");
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        const auto f = ape_escape_tsv_columns(line); if (f.size() < 7) continue;
        const int id = static_cast<int>(ape_escape_monke_number(f[0]));
        const int n = static_cast<int>(ape_escape_monke_number(f[2]));
        const int level = static_cast<int>(ape_escape_monke_number(f[4]));
        auto it = std::find_if(s_ape_monke_stages.begin(), s_ape_monke_stages.end(),
            [id](const ApeMonkeStage& v) { return v.id == id; });
        if (it == s_ape_monke_stages.end()) {
            s_ape_monke_stages.push_back({id, f[1], 0}); it = s_ape_monke_stages.end() - 1;
        }
        if (n <= 0) continue;
        s_ape_monke_entries.push_back({id, n, level, f[1], f[3], f[5], f[6]}); ++it->entries;
    }
    if (!s_ape_monke_stages.empty() && !ape_escape_monke_stage(s_ape_monke_stage))
        s_ape_monke_stage = s_ape_monke_stages.front().id;
}
static void ape_escape_load_run_history() {
    if (s_ape_run_history_loaded) return;
    s_ape_run_history_loaded = true;
    std::ifstream in(ape_escape_data_directory() / "ape_escape_journal.tsv"); std::string line;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        const auto f = ape_escape_tsv_columns(line); if (f.size() < 8) continue;
        ApeRunRecord r;
        r.stage = static_cast<int>(ape_escape_monke_number(f[0]));
        r.timestamp = static_cast<std::int64_t>(ape_escape_monke_number(f[1]));
        r.frames = static_cast<unsigned>(ape_escape_monke_number(f[2]));
        r.caught = static_cast<unsigned>(ape_escape_monke_number(f[3]));
        r.triangles = static_cast<unsigned>(ape_escape_monke_number(f[4]));
        r.coins = static_cast<unsigned>(ape_escape_monke_number(f[5]));
        r.lives = static_cast<unsigned>(ape_escape_monke_number(f[6]));
        r.mask = static_cast<std::uint32_t>(ape_escape_monke_number(f[7], 16));
        s_ape_run_history.push_back(r); s_ape_ever_caught[r.stage] |= r.mask;
        const auto best = s_ape_stage_bests.find(r.stage);
        if (r.frames && (best == s_ape_stage_bests.end() || r.frames < best->second.frames))
            s_ape_stage_bests[r.stage] = r;
    }
    if (s_ape_run_history.size() > 1000u)
        s_ape_run_history.erase(s_ape_run_history.begin(), s_ape_run_history.end() - 1000);
}
static void ape_escape_refresh_run_history() {
    s_ape_run_history.clear();
    s_ape_ever_caught.clear();
    s_ape_stage_bests.clear();
    s_ape_run_history_loaded = false;
    ape_escape_load_run_history();
    s_ape_escape_quick_status = "Play history and time-trial records refreshed from local data.";
}
static bool ape_escape_export_time_trials() {
    ape_escape_load_run_history();
    const auto path = ape_escape_data_directory() / "ape_escape_time_trials.csv";
    std::ofstream out(path, std::ios::trunc);
    if (!out) {
        s_ape_escape_quick_status = "Could not export time-trial CSV.";
        return false;
    }
    out << "stage_id,stage_name,best_observed_frames,best_observed_time,captured,triangles,specter_coins,lives,timestamp\n";
    for (const auto& stage : s_ape_monke_stages) {
        const auto found = s_ape_stage_bests.find(stage.id);
        if (found == s_ape_stage_bests.end()) continue;
        const auto& r = found->second;
        std::string name = stage.name;
        std::string escaped;
        escaped.reserve(name.size() + 2u);
        escaped.push_back('"');
        for (const char ch : name) {
            if (ch == '"') escaped.push_back('"');
            escaped.push_back(ch);
        }
        escaped.push_back('"');
        out << r.stage << ',' << escaped << ',' << r.frames << ','
            << ape_escape_time_string(r.frames) << ',' << r.caught << ','
            << r.triangles << ',' << r.coins << ',' << r.lives << ','
            << ape_escape_date_string(r.timestamp) << '\n';
    }
    out.close();
    if (!out) {
        s_ape_escape_quick_status = "Could not finish exporting time-trial CSV.";
        return false;
    }
    s_ape_escape_quick_status = "Exported time-trial records to ape_escape_time_trials.csv.";
    return true;
}
static void ape_escape_clear_run_history() {
    std::error_code ec;
    std::filesystem::remove(ape_escape_data_directory() / "ape_escape_journal.tsv", ec);
    if (ec) { s_ape_escape_quick_status = "Could not clear history: " + ec.message(); return; }
    s_ape_run_history.clear(); s_ape_ever_caught.clear(); s_ape_stage_bests.clear();
    s_ape_escape_quick_status = "Local history and recorded progress cleared.";
}
static std::string ape_escape_monke_lower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(),
        [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return value;
}
static void ape_escape_draw_monke_pedia(LauncherModel*, const LauncherTheme& th) {
    ape_escape_load_monke_catalog(); ape_escape_load_run_history();
    ImGui::TextColored(col(th.accent2), "MONKEPEDIA");
    ImGui::TextWrapped("The Monkey Book for the original 1999 North-American game. Each listed profile includes a source link. Profiles without a fully verified US name and description are intentionally omitted rather than guessed.");
    const float gap = px(7.0f), bw = px(135.0f);
    if (ImGui::Button("Monkepedia", ImVec2(bw, px(30)))) s_ape_monke_page = 0;
    ImGui::SameLine(0, gap);
    if (ImGui::Button("Play History", ImVec2(bw, px(30)))) s_ape_monke_page = 1;
    ImGui::SameLine(0, gap);
    if (ImGui::Button("Time Trials", ImVec2(bw, px(30)))) s_ape_monke_page = 2;
    ImGui::Separator();
    if (s_ape_monke_page == 0) {
        if (s_ape_monke_stages.empty()) {
            ImGui::TextWrapped("Catalogue missing: assets/monkepedia.tsv was not found. Reinstall the app."); return;
        }
        unsigned captured = 0, trackable = 0;
        for (const auto& st : s_ape_monke_stages) {
            const unsigned n = static_cast<unsigned>(std::min(st.entries, 20));
            const std::uint32_t mask = s_ape_ever_caught[st.id];
            captured += ape_escape_mask_count(mask & (n ? ((1u << n) - 1u) : 0u)); trackable += n;
        }
        ImGui::Text("Recorded captures: %u / %u listed, trackable profiles", captured, trackable);
        ImGui::TextDisabled("Static entries are always available. Enable Progress Journal under Mods to save local progress.");
        const float leftw = std::max(px(205.0f), ImGui::GetContentRegionAvail().x * 0.36f);
        ImGui::BeginChild("ape_monke_stages", ImVec2(leftw, px(390)), ImGuiChildFlags_Borders);
        ImGui::TextColored(col(th.accent2), "STAGES");
        for (const auto& st : s_ape_monke_stages) {
            const unsigned n = static_cast<unsigned>(std::min(st.entries, 20));
            const std::uint32_t mask = s_ape_ever_caught[st.id];
            const unsigned c = ape_escape_mask_count(mask & (n ? ((1u << n) - 1u) : 0u));
            char label[160];
            if (st.entries) std::snprintf(label, sizeof(label), "%s  %u/%u", st.name.c_str(), c, n);
            else std::snprintf(label, sizeof(label), "%s  (challenge)", st.name.c_str());
            if (ImGui::Selectable(label, s_ape_monke_stage == st.id)) {
                s_ape_monke_stage = st.id; s_ape_monke_entry = 1; s_ape_monke_search[0] = '\0';
            }
        }
        ImGui::EndChild(); ImGui::SameLine(0, gap);
        ImGui::BeginChild("ape_monke_entries", ImVec2(0, px(390)), ImGuiChildFlags_Borders);
        const auto* st = ape_escape_monke_stage(s_ape_monke_stage);
        if (st) {
            ImGui::TextColored(col(th.accent2), "%s", st->name.c_str());
            ImGui::SetNextItemWidth(-1);
            ImGui::InputText("Search##monkepedia", s_ape_monke_search, sizeof(s_ape_monke_search));
            const std::string q = ape_escape_monke_lower(s_ape_monke_search);
            const std::uint32_t mask = s_ape_ever_caught[st->id]; bool selected_exists = false;
            for (const auto& e : s_ape_monke_entries) {
                if (e.stage != st->id) continue;
                const std::string hay = ape_escape_monke_lower(e.name + " " + e.description + " " + e.stage_name);
                if (!q.empty() && hay.find(q) == std::string::npos) continue;
                const bool can_track = e.index <= 20;
                const bool caught = can_track && (mask & (1u << (e.index - 1))) != 0u;
                char label[256];
                std::snprintf(label, sizeof(label), "%02d  %s%s", e.index, e.name.c_str(),
                    !can_track ? "  [NOT TRACKED]" : (caught ? "  [CAUGHT]" : ""));
                if (ImGui::Selectable(label, s_ape_monke_entry == e.index)) {
                    s_ape_monke_entry = e.index; selected_exists = true;
                }
                if (s_ape_monke_entry == e.index) selected_exists = true;
            }
            if (!selected_exists) s_ape_monke_entry = 0;
            const auto e = std::find_if(s_ape_monke_entries.begin(), s_ape_monke_entries.end(),
                [&](const ApeMonkeEntry& v) { return v.stage == s_ape_monke_stage && v.index == s_ape_monke_entry; });
            if (e != s_ape_monke_entries.end()) {
                ImGui::Separator(); ImGui::TextColored(col(th.accent), "%s", e->name.c_str());
                ImGui::Text("Stage entry: %02d", e->index);
                ImGui::Text("Monkey Level: %d", e->monkey_level);
                ImGui::TextWrapped("Profile description: %s", e->description.c_str());
                if (e->index > 20) ImGui::TextWrapped("The current game-state observer tracks at most 20 capture flags.");
                else if (mask & (1u << (e->index - 1))) ImGui::TextColored(col(th.good), "Captured in at least one recorded run.");
                else ImGui::TextDisabled("No capture was observed in the local recorded history.");
                if (ImGui::Button("View source profile", ImVec2(px(170), px(30))))
                    ape_escape_open_url(e->source_url);
            }
        }
        ImGui::EndChild();
    } else if (s_ape_monke_page == 1) {
        ImGui::TextColored(col(th.accent2), "PLAY HISTORY & PROGRESS");
        ImGui::TextWrapped("Stage exits are stored locally. No history is uploaded and the journal never writes to game RAM.");
        if (ImGui::Button("Refresh History", ImVec2(px(150), px(30))))
            ape_escape_refresh_run_history();
        ImGui::SameLine(0, gap);
        ImGui::Text("Recorded stage exits: %u", static_cast<unsigned>(s_ape_run_history.size()));
        ImGui::Text("Stages with an observed best: %u", static_cast<unsigned>(s_ape_stage_bests.size()));
        ImGui::Separator();
        if (s_ape_run_history.empty()) {
            ImGui::TextWrapped("No history yet. Enable Progress Journal in Mods, play a stage, and exit it normally.");
        } else {
            const std::size_t first = s_ape_run_history.size() > 20u ? s_ape_run_history.size() - 20u : 0u;
            for (std::size_t i = s_ape_run_history.size(); i > first; --i) {
                const auto& r = s_ape_run_history[i - 1];
                ImGui::Text("%s | %s | %s | %u captured", ape_escape_date_string(r.timestamp).c_str(),
                    ape_escape_monke_stage_name(r.stage).c_str(), ape_escape_time_string(r.frames).c_str(), r.caught);
                ImGui::TextDisabled("Triangles %u   Specter coins %u   Lives %u", r.triangles, r.coins, r.lives);
                ImGui::Separator();
            }
        }
        if (ImGui::Button("Open History File", ImVec2(px(170), px(32)))) {
            const auto path = ape_escape_data_directory() / "ape_escape_journal.tsv";
            if (std::filesystem::is_regular_file(path)) ape_escape_open_url(ape_escape_file_url(path));
            else s_ape_escape_quick_status = "No history file exists yet.";
        }
        ImGui::SameLine(0, gap);
        if (ImGui::Button("Clear History...", ImVec2(px(145), px(32)))) ImGui::OpenPopup("Clear Local Ape Escape History");
        if (ImGui::BeginPopupModal("Clear Local Ape Escape History", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
            ImGui::TextWrapped("Delete local attempts and recorded captured-entry progress?");
            if (ImGui::Button("Cancel", ImVec2(px(90), px(30)))) ImGui::CloseCurrentPopup();
            ImGui::SameLine();
            if (ImGui::Button("Delete History", ImVec2(px(125), px(30)))) {
                ape_escape_clear_run_history(); ImGui::CloseCurrentPopup();
            }
            ImGui::EndPopup();
        }
    } else {
        ImGui::TextColored(col(th.accent2), "TIME TRIALS");
        ImGui::TextWrapped("Fastest observed stage-exit timer using the game's 60 Hz clock. These are practice records, not certified speedrun results: this version cannot verify successful clears, assist-mod use or retry semantics.");
        if (ImGui::Button("Refresh Records", ImVec2(px(150), px(30))))
            ape_escape_refresh_run_history();
        ImGui::SameLine(0, gap);
        if (ImGui::Button("Export CSV", ImVec2(px(120), px(30))))
            (void)ape_escape_export_time_trials();
        if (s_ape_stage_bests.empty()) ImGui::TextDisabled("No records yet. Enable Progress Journal in Mods and play a stage.");
        else if (ImGui::BeginTable("ape_monke_times", 4, ImGuiTableFlags_Borders | ImGuiTableFlags_RowBg | ImGuiTableFlags_Resizable)) {
            ImGui::TableSetupColumn("Stage"); ImGui::TableSetupColumn("Best observed");
            ImGui::TableSetupColumn("Captured"); ImGui::TableSetupColumn("Last record");
            ImGui::TableHeadersRow();
            for (const auto& st : s_ape_monke_stages) {
                const auto found = s_ape_stage_bests.find(st.id); if (found == s_ape_stage_bests.end()) continue;
                const auto& r = found->second;
                ImGui::TableNextRow();
                ImGui::TableSetColumnIndex(0); ImGui::TextUnformatted(st.name.c_str());
                ImGui::TableSetColumnIndex(1); ImGui::TextUnformatted(ape_escape_time_string(r.frames).c_str());
                ImGui::TableSetColumnIndex(2); ImGui::Text("%u / %d", r.caught, st.entries);
                ImGui::TableSetColumnIndex(3); ImGui::TextUnformatted(ape_escape_date_string(r.timestamp).c_str());
            }
            ImGui::EndTable();
        }
    }
    if (!s_ape_escape_quick_status.empty()) {
        ImGui::Spacing(); ImGui::TextWrapped("%s", s_ape_escape_quick_status.c_str());
    }
}
'''

QUICK_TOOLS = r'''
    // APE_ESCAPE_QUICK_TOOLS
    ImGui::Spacing();
    ImGui::Separator();
    ImGui::TextColored(col(th.accent2), "QUICK TOOLS");
    if (m->rom_present && m->rom_full[0]) {
        ImGui::TextWrapped("Selected disc: %s", m->rom_full);
        const bool disc_verified = launcher_model_rom_verified(m);
        ImGui::TextColored(col(disc_verified ? th.good : th.warn),
                           "Disc verification: %s",
                           disc_verified ? "Verified" : "Not verified");
    } else {
        ImGui::TextDisabled("No disc selected yet.");
        ImGui::TextDisabled("Disc verification is unavailable until a disc is selected.");
    }
    ImGui::TextWrapped("Open your data, save, and disc folders, or inspect your installed build.");
    const std::string build_info = ape_escape_build_info();
    ImGui::TextWrapped("%s", build_info.c_str());
    const float quick_gap = px(8.0f);
    float quick_button_w = (ImGui::GetContentRegionAvail().x - quick_gap) * 0.5f;
    if (quick_button_w < px(115.0f)) quick_button_w = px(115.0f);
    if (ImGui::Button("Open Data Folder", ImVec2(quick_button_w, px(34.0f))))
        ape_escape_open_folder(ape_escape_data_directory());
    ImGui::SameLine(0, quick_gap);
    if (ImGui::Button("Open Save Folder", ImVec2(quick_button_w, px(34.0f))))
        ape_escape_open_folder(ape_escape_application_directory() / "saves");
    if (ImGui::Button("Open Disc Folder", ImVec2(quick_button_w, px(34.0f))))
        ape_escape_open_disc_folder(m);
    ImGui::SameLine(0, quick_gap);
    if (ImGui::Button("Copy Build Info", ImVec2(quick_button_w, px(34.0f)))) {
        ImGui::SetClipboardText(build_info.c_str());
        s_ape_escape_quick_status = "Build information copied to the clipboard.";
    }
    if (ImGui::Button("Nightly / Update History", ImVec2(quick_button_w, px(34.0f))))
        ape_escape_open_nightly_page();
    if (!s_ape_escape_quick_status.empty())
        ImGui::TextWrapped("%s", s_ape_escape_quick_status.c_str());
'''

OLD_UI_DEFAULTS = r'''static const SDL_Scancode kPsxDefaults[LNG_PSX_PAD_BUTTON_COUNT] = {
    /* Up */ SDL_SCANCODE_UP, /* Down */ SDL_SCANCODE_DOWN,
    /* Left */ SDL_SCANCODE_LEFT, /* Right */ SDL_SCANCODE_RIGHT,
    /* Triangle */ SDL_SCANCODE_A, /* Circle */ SDL_SCANCODE_S,
    /* Cross */ SDL_SCANCODE_X, /* Square */ SDL_SCANCODE_Z,
    /* L1 */ SDL_SCANCODE_Q, /* L2 */ SDL_SCANCODE_E,
    /* R1 */ SDL_SCANCODE_W, /* R2 */ SDL_SCANCODE_R,
    /* L3 */ SDL_SCANCODE_T, /* R3 */ SDL_SCANCODE_Y,
    /* Start */ SDL_SCANCODE_RETURN, /* Select */ SDL_SCANCODE_RSHIFT,
    /* LS Up */ SDL_SCANCODE_UP, /* LS Down */ SDL_SCANCODE_DOWN,
    /* LS Left */ SDL_SCANCODE_LEFT, /* LS Right */ SDL_SCANCODE_RIGHT,
    /* RS Up */ SDL_SCANCODE_UNKNOWN, /* RS Down */ SDL_SCANCODE_UNKNOWN,
    /* RS Left */ SDL_SCANCODE_UNKNOWN, /* RS Right */ SDL_SCANCODE_UNKNOWN,
};'''
NEW_UI_DEFAULTS = r'''/* APE_ESCAPE_CUSTOM_KEYBOARD_DEFAULTS: legacy snapshot for safe one-time migration. */
static const SDL_Scancode kPsxLegacyDefaults[LNG_PSX_PAD_BUTTON_COUNT] = {
    /* Up */ SDL_SCANCODE_UP, /* Down */ SDL_SCANCODE_DOWN,
    /* Left */ SDL_SCANCODE_LEFT, /* Right */ SDL_SCANCODE_RIGHT,
    /* Triangle */ SDL_SCANCODE_A, /* Circle */ SDL_SCANCODE_S,
    /* Cross */ SDL_SCANCODE_X, /* Square */ SDL_SCANCODE_Z,
    /* L1 */ SDL_SCANCODE_Q, /* L2 */ SDL_SCANCODE_E,
    /* R1 */ SDL_SCANCODE_W, /* R2 */ SDL_SCANCODE_R,
    /* L3 */ SDL_SCANCODE_T, /* R3 */ SDL_SCANCODE_Y,
    /* Start */ SDL_SCANCODE_RETURN, /* Select */ SDL_SCANCODE_RSHIFT,
    /* LS Up */ SDL_SCANCODE_UP, /* LS Down */ SDL_SCANCODE_DOWN,
    /* LS Left */ SDL_SCANCODE_LEFT, /* LS Right */ SDL_SCANCODE_RIGHT,
    /* RS Up */ SDL_SCANCODE_UNKNOWN, /* RS Down */ SDL_SCANCODE_UNKNOWN,
    /* RS Left */ SDL_SCANCODE_UNKNOWN, /* RS Right */ SDL_SCANCODE_UNKNOWN,
};
static const SDL_Scancode kPsxDefaults[LNG_PSX_PAD_BUTTON_COUNT] = {
    /* D-pad: T / G / F / H */
    /* Up */ SDL_SCANCODE_T, /* Down */ SDL_SCANCODE_G,
    /* Left */ SDL_SCANCODE_F, /* Right */ SDL_SCANCODE_H,
    /* Triangle */ SDL_SCANCODE_V, /* Circle */ SDL_SCANCODE_C,
    /* Cross */ SDL_SCANCODE_X, /* Square */ SDL_SCANCODE_Z,
    /* L1 */ SDL_SCANCODE_Q, /* L2 */ SDL_SCANCODE_E,
    /* R1 */ SDL_SCANCODE_SPACE, /* R2 */ SDL_SCANCODE_R,
    /* L3 */ SDL_SCANCODE_Y, /* R3 */ SDL_SCANCODE_U,
    /* Start */ SDL_SCANCODE_RETURN, /* Select */ SDL_SCANCODE_LSHIFT,
    /* Left stick: W / S / A / D */
    /* LS Up */ SDL_SCANCODE_W, /* LS Down */ SDL_SCANCODE_S,
    /* LS Left */ SDL_SCANCODE_A, /* LS Right */ SDL_SCANCODE_D,
    /* Right stick: arrow keys */
    /* RS Up */ SDL_SCANCODE_UP, /* RS Down */ SDL_SCANCODE_DOWN,
    /* RS Left */ SDL_SCANCODE_LEFT, /* RS Right */ SDL_SCANCODE_RIGHT,
};'''


PSX_MIGRATION_MARKER = "APE_ESCAPE_MIGRATE_DEFAULT_KEYBOARD_LAYOUT"
PSX_MIGRATION_FUNCTION = r'''
/* APE_ESCAPE_MIGRATE_DEFAULT_KEYBOARD_LAYOUT
 * Upgrade only slots whose entire map is still the previous generated default.
 * Any player-edited bind or alternate stops migration for that slot. */
static int psx_kb_migrate_legacy_defaults(void) {
    int changed = 0;
    for (int p = 0; p < PSX_BINDS_MAX_PLAYERS; ++p) {
        int is_legacy_default = 1;
        for (int b = 0; b < LNG_PSX_PAD_BUTTON_COUNT; ++b) {
            if (s_psx_binds[p][b] != kPsxLegacyDefaults[b] ||
                s_psx_binds_alt[p][b] != SDL_SCANCODE_UNKNOWN) {
                is_legacy_default = 0;
                break;
            }
        }
        if (is_legacy_default) {
            memcpy(s_psx_binds[p], kPsxDefaults, sizeof(kPsxDefaults));
            changed = 1;
        }
    }
    return changed;
}
'''

OLD_RUNTIME_DEFAULTS = r'''/*
 * Every player slot uses the framework's historical hardcoded keyboard mapping
 * (pad_from_keyboard / pad_sticks_for in main.cpp):
 *   D-pad: Arrow keys      Start: Return     Select: Right Shift
 *   Cross: X   Circle: S   Square: Z   Triangle: A
 *   L1: Q  R1: W  L2: E  R2: R  L3: T  R3: Y
 *   Left analog stick: Arrow keys
 *   Right analog stick: unbound
 * Simultaneous multi-keyboard play still requires distinct binds per slot.
 */
#define PSXKB_PLAYER_DEFAULTS { \\
    .up = SDL_SCANCODE_UP, .down = SDL_SCANCODE_DOWN, \\
    .left = SDL_SCANCODE_LEFT, .right = SDL_SCANCODE_RIGHT, \\
    .cross = SDL_SCANCODE_X, .circle = SDL_SCANCODE_S, \\
    .square = SDL_SCANCODE_Z, .triangle = SDL_SCANCODE_A, \\
    .l1 = SDL_SCANCODE_Q, .r1 = SDL_SCANCODE_W, \\
    .l2 = SDL_SCANCODE_E, .r2 = SDL_SCANCODE_R, \\
    .l3 = SDL_SCANCODE_T, .r3 = SDL_SCANCODE_Y, \\
    .start = SDL_SCANCODE_RETURN, .select = SDL_SCANCODE_RSHIFT, \\
    .ls_up = SDL_SCANCODE_UP, .ls_down = SDL_SCANCODE_DOWN, \\
    .ls_left = SDL_SCANCODE_LEFT, .ls_right = SDL_SCANCODE_RIGHT, \\
    .rs_up = SDL_SCANCODE_UNKNOWN, .rs_down = SDL_SCANCODE_UNKNOWN, \\
    .rs_left = SDL_SCANCODE_UNKNOWN, .rs_right = SDL_SCANCODE_UNKNOWN, \\
}'''
NEW_RUNTIME_DEFAULTS = r'''/*
 * Ape Escape keyboard defaults: D-pad T/G/F/H, left stick W/S/A/D,
 * right stick arrow keys, R1 Space, Cross/Circle/Square/Triangle X/C/Z/V,
 * L1/L2 Q/E, Start Return, Select Shift, R2 R and L3/R3 Y/U.
 * Simultaneous multi-keyboard play still requires distinct binds per slot.
 */
#define PSXKB_PLAYER_DEFAULTS /* APE_ESCAPE_CUSTOM_KEYBOARD_DEFAULTS */ { \
    .up = SDL_SCANCODE_T, .down = SDL_SCANCODE_G, \
    .left = SDL_SCANCODE_F, .right = SDL_SCANCODE_H, \
    .cross = SDL_SCANCODE_X, .circle = SDL_SCANCODE_C, \
    .square = SDL_SCANCODE_Z, .triangle = SDL_SCANCODE_V, \
    .l1 = SDL_SCANCODE_Q, .r1 = SDL_SCANCODE_SPACE, \
    .l2 = SDL_SCANCODE_E, .r2 = SDL_SCANCODE_R, \
    .l3 = SDL_SCANCODE_Y, .r3 = SDL_SCANCODE_U, \
    .start = SDL_SCANCODE_RETURN, .select = SDL_SCANCODE_LSHIFT, \
    .ls_up = SDL_SCANCODE_W, .ls_down = SDL_SCANCODE_S, \
    .ls_left = SDL_SCANCODE_A, .ls_right = SDL_SCANCODE_D, \
    .rs_up = SDL_SCANCODE_UP, .rs_down = SDL_SCANCODE_DOWN, \
    .rs_left = SDL_SCANCODE_LEFT, .rs_right = SDL_SCANCODE_RIGHT, \
}'''

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

    # Make the standard-library streams needed by the per-user preferences available.
    if PREFS_INCLUDE_MARKER not in launcher_text:
        if args.check:
            return fail("The launcher preference include has not been applied.", 1)
        if launcher_text.count(INCLUDE_ANCHOR) != 1:
            return fail("Pinned launcher source no longer matches the guarded preference include anchor.")
        launcher_text = launcher_text.replace(
            INCLUDE_ANCHOR,
            INCLUDE_ANCHOR + "\n#include <fstream> // " + PREFS_INCLUDE_MARKER,
            1,
        )

    # Standard-library utilities used by the Monkey Book and journal view.
    if "APE_ESCAPE_MONKEPEDIA_INCLUDES" not in launcher_text:
        if args.check:
            return fail("Monkepedia standard-library includes have not been applied.", 1)
        launcher_text = launcher_text.replace(
            INCLUDE_ANCHOR,
            INCLUDE_ANCHOR + "\n#include <algorithm> // APE_ESCAPE_MONKEPEDIA_INCLUDES\n#include <cctype>\n#include <cstdint>\n#include <ctime>\n#include <sstream>",
            1,
        )

    # Declare per-user preferences before draw_crt_background reads reduce_motion.
    if PREFS_MARKER not in launcher_text:
        if args.check:
            return fail("Accessibility preference helpers have not been applied.", 1)
        state_anchor = "void draw_crt_background(ImVec2 origin, ImVec2 size) {"
        if launcher_text.count(state_anchor) != 1:
            return fail("Pinned launcher source no longer matches the guarded accessibility-state anchor.")
        launcher_text = launcher_text.replace(state_anchor, PREFS_STATE + state_anchor, 1)
        if launcher_text.count(DRAW_ANCHOR) != 1:
            return fail("Pinned launcher source no longer matches the guarded accessibility-helper anchor.")
        launcher_text = launcher_text.replace(DRAW_ANCHOR, PREFS_HELPER + "\n" + DRAW_ANCHOR, 1)
    elif "ape_escape_draw_accessibility_settings" not in launcher_text:
        return fail("Accessibility preferences exist but their settings UI is missing.")

    # The Monkey Book is a dedicated launcher view with local journal subpages.
    model_path = ui_root / MODEL_HEADER
    if not model_path.is_file():
        return fail("Required launcher model header is missing.", 2)
    model_text = model_path.read_text(encoding="utf-8")
    if MONKEPEDIA_VIEW_MARKER not in model_text:
        if args.check:
            return fail("Monkepedia view enum has not been applied.", 1)
        enum_anchor = "    LNG_VIEW_CREDITS,"
        if model_text.count(enum_anchor) != 1:
            return fail("Pinned launcher model no longer matches the guarded Monkepedia enum anchor.")
        model_text = model_text.replace(
            enum_anchor, enum_anchor + "\n    LNG_VIEW_MONKEPEDIA, /* " + MONKEPEDIA_VIEW_MARKER + " */", 1)
        model_path.write_text(model_text, encoding="utf-8")

    helper_marker = "APE_ESCAPE_MONKEPEDIA_HELPER"
    if helper_marker not in launcher_text:
        if args.check:
            return fail("Monkepedia helper has not been applied.", 1)
        if launcher_text.count(DRAW_ANCHOR) != 1:
            return fail("Pinned launcher no longer matches the guarded Monkepedia helper anchor.")
        launcher_text = launcher_text.replace(DRAW_ANCHOR, MONKEPEDIA_HELPER + "\n" + DRAW_ANCHOR, 1)

    nav_marker = "APE_ESCAPE_MONKEPEDIA_NAV"
    if nav_marker not in launcher_text:
        if args.check:
            return fail("Monkepedia navigation has not been applied.", 1)
        old_nav = (
            "            const int count = 1 + (m->mods ? 1 : 0) +\n"
            "                              (m->has_assist_tools ? 1 : 0) +\n"
            "                              ((m->credits_text && m->credits_text[0]) ? 1 : 0);\n"
            "            const float w = px(110.0f);\n"
            "            const float total = w * count + gap * (count - 1);\n"
            "            ImGui::SetCursorPos(ImVec2(right - total, y));\n"
            "            if (ImGui::Button(ui_text(\"Settings\"), ImVec2(w, px(34))))\n"
            "                launcher_model_set_view(m, LNG_VIEW_SETTINGS);"
        )
        new_nav = (
            "            /* APE_ESCAPE_MONKEPEDIA_NAV */\n"
            "            const int count = 2 + (m->mods ? 1 : 0) +\n"
            "                              (m->has_assist_tools ? 1 : 0) +\n"
            "                              ((m->credits_text && m->credits_text[0]) ? 1 : 0);\n"
            "            const float w = px(96.0f);\n"
            "            const float total = w * count + gap * (count - 1);\n"
            "            ImGui::SetCursorPos(ImVec2(right - total, y));\n"
            "            if (ImGui::Button(ui_text(\"Settings\"), ImVec2(w, px(34))))\n"
            "                launcher_model_set_view(m, LNG_VIEW_SETTINGS);\n"
            "            ImGui::SameLine(0, gap);\n"
            "            if (ImGui::Button(\"Monkepedia\", ImVec2(w, px(34))))\n"
            "                launcher_model_set_view(m, LNG_VIEW_MONKEPEDIA);"
        )
        if launcher_text.count(old_nav) != 1:
            return fail("Pinned launcher navigation no longer matches the guarded Monkepedia nav anchor.")
        launcher_text = launcher_text.replace(old_nav, new_nav, 1)

    body_marker = "APE_ESCAPE_MONKEPEDIA_BODY"
    if body_marker not in launcher_text:
        if args.check:
            return fail("Monkepedia body dispatch has not been applied.", 1)
        body_anchor = "        case LNG_VIEW_CREDITS:      draw_credits(m, th);             break;"
        if launcher_text.count(body_anchor) != 1:
            return fail("Pinned launcher view switch no longer matches the guarded Monkepedia body anchor.")
        launcher_text = launcher_text.replace(
            body_anchor,
            body_anchor + "\n        case LNG_VIEW_MONKEPEDIA: /* " + body_marker + " */ ape_escape_draw_monke_pedia(m, th); break;",
            1)

    # Add the accessibility card at the end of the Settings page.
    if ACCESSIBILITY_MARKER not in launcher_text:
        if args.check:
            return fail("The accessibility settings card has not been applied.", 1)
        if launcher_text.count(SETTINGS_ANCHOR) != 1:
            return fail("Pinned launcher settings no longer match the guarded accessibility card anchor.")
        launcher_text = launcher_text.replace(SETTINGS_ANCHOR, ACCESSIBILITY_INSERT + SETTINGS_ANCHOR, 1)

    # Keep quick folder actions and the release shortcut on the dashboard.
    if QUICK_TOOLS_MARKER not in launcher_text:
        if args.check:
            return fail("The dashboard quick-tools panel has not been applied.", 1)
        if launcher_text.count(END_ANCHOR) != 1:
            return fail("Pinned launcher dashboard no longer matches the guarded quick-tools anchor.")
        launcher_text = launcher_text.replace(END_ANCHOR, "\n" + QUICK_TOOLS + END_ANCHOR, 1)

    # Reduce visual effects through a stable, early-return path in the background painter.
    reduce_anchor = "    ImDrawList* bg = ImGui::GetBackgroundDrawList();\n"
    reduce_marker = "APE_ESCAPE_REDUCE_VISUAL_EFFECTS"
    if reduce_marker not in launcher_text:
        if args.check:
            return fail("Reduced visual effects have not been connected to the launcher background.", 1)
        if launcher_text.count(reduce_anchor) != 1:
            return fail("Pinned launcher background no longer matches the guarded reduced-effects anchor.")
        reduced = (
            reduce_anchor +
            "    // " + reduce_marker + ": replace gradients and scanlines with a flat surface.\n"
            "    if (g_ape_escape_preferences.reduce_motion) {\n"
            "        bg->AddRectFilled(origin, ImVec2(origin.x + size.x, origin.y + size.y), imcol(th.background));\n"
            "        return;\n"
            "    }\n"
        )
        launcher_text = launcher_text.replace(reduce_anchor, reduced, 1)

    # Make global theme/style changes affect the background, dashboard and all settings pages.
    call_anchor = "        LNG_ImplSDL_NewFrame();\n"
    draw_anchor_with_commit = (
        "        if (launch_commit.job.pending()) draw_launch_commit_progress(*th);\n"
        "        else draw_ui(m, *th, p->logical_w, p->logical_h);\n"
    )
    draw_anchor_direct = "        draw_ui(m, *th, p->logical_w, p->logical_h);\n"
    clear_anchor = "        const LngColor bg = th->background;\n"
    if ACCESS_THEME_MARKER not in launcher_text:
        if args.check:
            return fail("Global accessibility theme application has not been applied.", 1)
        if launcher_text.count(call_anchor) != 1:
            return fail("Pinned launcher frame loop no longer matches the guarded accessibility frame anchor.")
        if launcher_text.count(clear_anchor) != 1:
            return fail("Pinned launcher frame loop no longer matches the guarded accessibility clear-color anchor.")
        if launcher_text.count(draw_anchor_with_commit) == 1:
            selected_draw_anchor = draw_anchor_with_commit
            draw_replacement = (
                "        if (launch_commit.job.pending()) draw_launch_commit_progress(*g_th);\n"
                "        else draw_ui(m, *g_th, p->logical_w, p->logical_h);\n"
            )
        elif launcher_text.count(draw_anchor_direct) == 1:
            selected_draw_anchor = draw_anchor_direct
            draw_replacement = "        draw_ui(m, *g_th, p->logical_w, p->logical_h);\n"
        else:
            return fail("Pinned launcher frame loop no longer matches a supported guarded draw anchor.")
        launcher_text = launcher_text.replace(
            call_anchor,
            "        ape_escape_refresh_accessibility_theme(th); // " + ACCESS_THEME_MARKER + "\n" + call_anchor,
            1,
        )
        launcher_text = launcher_text.replace(selected_draw_anchor, draw_replacement, 1)
        launcher_text = launcher_text.replace(
            clear_anchor, "        const LngColor bg = g_th->background;\n", 1
        )
    elif ("draw_ui(m, *g_th, p->logical_w, p->logical_h)" not in launcher_text or
          "const LngColor bg = g_th->background;" not in launcher_text):
        return fail("Accessibility theme marker exists but the frame loop is not using the effective theme.")

    # Load preferences after ImGui exists, and point the shared background helpers at the same theme copy.
    run_anchor = "    g_th = th;\n"
    run_marker = "APE_ESCAPE_INIT_ACCESSIBILITY_PREFERENCES"
    if run_marker not in launcher_text:
        if args.check:
            return fail("Accessibility preferences are not loaded before the first frame.", 1)
        if launcher_text.count(run_anchor) != 1:
            return fail("Pinned launcher startup no longer matches the guarded accessibility initialization anchor.")
        launcher_text = launcher_text.replace(
            run_anchor,
            "    ape_escape_load_preferences(); // " + run_marker + "\n"
            "    ape_escape_refresh_accessibility_theme(th);\n",
            1,
        )

    # Patch both the launcher's Controls-page defaults and the runtime fallback.
    ui_binds_path = ui_root / UI_KEYBOARD
    if not ui_binds_path.is_file():
        return fail(f"Required PSX launcher keybind source is missing: {ui_binds_path}", 2)
    ui_binds_text = ui_binds_path.read_text(encoding="utf-8")
    ui_binds_changed = False
    if KEYBOARD_MARKER not in ui_binds_text:
        if args.check:
            return fail("The full Ape Escape keyboard default map has not been applied to the launcher.", 1)
        start = ui_binds_text.find("static const SDL_Scancode kPsxDefaults[LNG_PSX_PAD_BUTTON_COUNT]")
        end = ui_binds_text.find("};", start) + 2 if start >= 0 else -1
        if start < 0 or end <= start or ui_binds_text.find("static const SDL_Scancode kPsxDefaults", end) >= 0:
            return fail("Pinned PSX launcher keybind defaults no longer match the guarded keyboard-map anchor.")
        ui_binds_text = ui_binds_text[:start] + NEW_UI_DEFAULTS + ui_binds_text[end:]
        ui_binds_changed = True
    elif "/* RS Up */ SDL_SCANCODE_UP" not in ui_binds_text:
        # The marker alone is not enough: require the right-stick arrow map to survive.
        return fail("Keyboard defaults are marked patched, but the right-stick mapping is missing.")

    # Safely migrate only old, untouched default layouts; edited maps stay intact.
    migration_anchor = "static void psx_kb_promote_empty_players(void) {"
    migration_tail = "\nvoid rui_psx_binds_init(const char* path) {"
    if PSX_MIGRATION_MARKER not in ui_binds_text:
        if args.check:
            return fail("Safe migration of legacy keyboard defaults has not been applied.", 1)
        if ui_binds_text.count(migration_anchor) != 1 or ui_binds_text.count(migration_tail) != 1:
            return fail("Pinned PSX keybind bridge no longer matches the guarded legacy-migration anchors.")
        # Place the migrator after the empty-player helper and before init.
        ui_binds_text = ui_binds_text.replace(
            migration_tail,
            "\n" + PSX_MIGRATION_FUNCTION + migration_tail,
            1,
        )
        old_init = "            psx_kb_promote_empty_players();"
        new_init = """            const int migrated_defaults = psx_kb_migrate_legacy_defaults();
            psx_kb_promote_empty_players();
            if (migrated_defaults) psx_kb_write_ini(path);"""
        if ui_binds_text.count(old_init) != 1:
            return fail("Pinned PSX keybind initialization no longer matches the guarded migration call site.")
        ui_binds_text = ui_binds_text.replace(old_init, new_init, 1)
        ui_binds_changed = True
    if ui_binds_changed:
        ui_binds_path.write_text(ui_binds_text, encoding="utf-8")

    runtime_binds_path = project_root / RUNTIME_KEYBOARD
    if not runtime_binds_path.is_file():
        return fail(f"Required PSX runtime keybind source is missing: {runtime_binds_path}", 2)
    runtime_binds_text = runtime_binds_path.read_text(encoding="utf-8")
    if KEYBOARD_MARKER not in runtime_binds_text:
        if args.check:
            return fail("The full Ape Escape keyboard default map has not been applied to the runtime.", 1)
        comment_start = runtime_binds_text.find("/*\n * Every player slot uses the framework's historical hardcoded keyboard mapping")
        macro_start = runtime_binds_text.find("#define PSXKB_PLAYER_DEFAULTS", comment_start)
        macro_end = runtime_binds_text.find("\n}", macro_start) + 2 if macro_start >= 0 else -1
        if comment_start < 0 or macro_start < 0 or macro_end <= macro_start:
            return fail("Pinned PSX runtime defaults no longer match the guarded keyboard-map anchor.")
        runtime_binds_text = runtime_binds_text[:comment_start] + NEW_RUNTIME_DEFAULTS + runtime_binds_text[macro_end:]
        runtime_binds_path.write_text(runtime_binds_text, encoding="utf-8")
    elif "SDL_SCANCODE_UP, .rs_up" not in runtime_binds_text and ".rs_up = SDL_SCANCODE_UP" not in runtime_binds_text:
        return fail("Runtime keyboard defaults are marked patched, but the right-stick arrow map is missing.")

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
        # Migrate any earlier patch state back to the manifest-owned PSX asset.
        ('/* brand             */ "ape_escape_logo.png",',
         '/* brand             */ "brand_psx.tga",'),
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
                               '/* brand             */ "brand_psx.tga",')
    if any(token not in profile_text for token in required_profile_tokens):
        return fail("Ape Escape PSX profile branding is incomplete.", 1)
    if profile_changed:
        profile_path.write_text(profile_text, encoding="utf-8")

    # The pinned launcher's asset manifest explicitly stages the PSX brand slot
    # from assets/consoles/psx/img/brand_psx.tga. Generate that exact runtime
    # asset from the transparent source PNG; arbitrary new filenames are ignored
    # by the manifest, which is why the former PNG never appeared in the header.
    try:
        logo_tga = png_to_tga(logo_source.read_bytes())
    except (OSError, ValueError, zlib.error, struct.error) as exc:
        return fail(f"Could not prepare the transparent Ape Escape logo: {exc}", 2)
    logo_dest.parent.mkdir(parents=True, exist_ok=True)
    same_logo = logo_dest.is_file() and logo_dest.read_bytes() == logo_tga
    if not same_logo:
        if args.check:
            return fail("Ape Escape TGA logo has not been staged in the PSX brand asset slot.", 1)
        logo_dest.write_bytes(logo_tga)

    if args.check:
        print("Ape Escape theme/logo, Monkepedia, local journal, rollback, accessibility, quick tools, and full keyboard defaults are present.")
    else:
        launcher_path.write_text(launcher_text, encoding="utf-8")
        print("Applied Ape Escape theme/logo, Monkepedia, local journal, rollback, and nvd123 Nightly updater patches.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
