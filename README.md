# Ape Escape Recompiled — nvd123

**Project maintainer: nvd123** · [Source code](https://github.com/NVDEMU/ApeEscapeRecomp-Mac) · [Releases](https://github.com/NVDEMU/ApeEscapeRecomp-Mac/releases)

A cross-platform native build of **Ape Escape (USA, SCUS-94423)**, maintained by nvd123 for macOS and Windows. The project uses static recompilation through the PSXRecomp framework to translate the original game's machine code into a native executable while retaining the PlayStation hardware model used by the runtime.

This is an actively developed preview, not a claim of a fully verified 100% playthrough. The original game disc is not included.

## Current status

The game boots through the introduction and title screens into playable levels. Dual-analog controls, memory-card saves, save states and rewind are available. Rendering uses OpenGL by default, with a Software renderer option.

| Feature | Status |
|---|---|
| macOS app | Apple Silicon and Intel builds |
| Windows app | Windows x64 ZIP package via GitHub Actions |
| Game boot and gameplay | Playable preview |
| DualShock / dual-analog controls | Supported |
| Memory-card save/load | Supported |
| Save states and rewind | Available in the launcher |
| Widescreen | Optional 16:9, 21:9 and Adaptive modes |
| Interpolated rendering | Optional; requires OpenGL |
| Built-in mod catalog | Optional features selected in the launcher |
| Complete playthrough | Not yet verified end-to-end |

## Built-in mods

**Every mod feature is disabled by default.** Enable only the features you want from the launcher's **Mods** page before starting the game. Keeping a mod in the catalog does not activate it.

- **Widescreen** — choose 16:9, 21:9 or Adaptive window aspect.
- **Interpolated Rendering** — redraw intermediate camera and model transforms at a selected presentation rate. Game logic, timers, input and audio retain their normal cadence; requires OpenGL.
- **PGXP Precision** — optional subpixel geometry and perspective-correct texture handling.
- **Skip FMVs** — fast-forward full-motion videos through their normal game-side completion path.
- **Quick Gadget Select** — a gadget-row shortcut inspired by later Ape Escape games.
- **Gameplay Assist Pack** — independently toggle Infinite Lives, Infinite Health, Infinite Air and Unlock All Gadgets. These assists only write during active gameplay and are opt-in.

The widescreen mode can reveal distance pop-in inherited from the original game. The optional **Extended Draw Distance** mod clamps ten traced GTE depth-bucket paths into the last safe ordering-table range rather than raising the game's bounds. It is experimental: it may change the original look or increase rendering work, and other game-side culling can still cause pop-in. Keep it off for stock behavior, and disable it if you see visual glitches. See [ISSUES.md](ISSUES.md) for remaining work.

The launcher's Video settings also expose internal resolution, antialiasing, texture filtering and FMV filtering. Higher internal resolutions can improve the final presentation, but returning to 1x can help on demanding scenes.

## Downloads and in-app Nightly updates

Nightly releases are published to this repository and include Windows x64 and
macOS Apple Silicon/Intel ZIP packages (plus DMGs for macOS). Use the launcher's
**Check for Nightly Updates** action to check this repository's `macos-nightly`
release, download the package matching your platform, verify its SHA-256
checksum, and install it only after closing the app. Windows updates preserve
`saves/`, `settings.toml`, and unknown/user-added files. Mac settings and saves
remain outside the .app bundle.

The first build containing the updater must be installed manually from
[Releases](https://github.com/NVDEMU/ApeEscapeRecomp-Mac/releases), because older
builds do not include the launcher button or updater helper. Failed or invalid
downloads are not installed.

## Playing on macOS

1. Download the ZIP or DMG that matches your Mac's processor from [Releases](https://github.com/NVDEMU/ApeEscapeRecomp-Mac/releases).
2. Open **Ape Escape Recompiled.app**. The builds are ad-hoc signed and not notarized, so macOS may ask you to confirm that you want to open the app.
3. In the launcher, select a legally obtained **Ape Escape (USA)** CUE/BIN disc image. Choose the **.cue** file; do not convert it to a cooked 2048-byte ISO, because the original disc sectors contain data used by FMV and audio playback.
4. Optionally select a legally obtained retail **SCPH1001.BIN** BIOS. OpenBIOS is included and selected automatically by default.
5. Open **Mods**, enable only the features you want, adjust video/controller settings, then launch.

A DualShock-compatible analog controller is recommended: the left stick moves Spike and the right stick controls the net. Keyboard input is also available. Save data and settings live outside the app bundle in your user Application Support directory.

## Project builds

GitHub Actions checks packaging syntax and tests the built-in mod catalog on every push. Successful pushes to `master` publish a shared Windows x64 + macOS Nightly release; a `macos-v*` tag publishes a versioned release. GitHub Actions builds Windows x64, Apple Silicon, and Intel Mac packages, then publishes SHA-256 sidecars and a Nightly manifest used by the in-app updater.

The build uses an original-disc CHD kept outside the public source tree. CI can download it through the private Dropbox secrets `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET` and `DROPBOX_REFRESH_TOKEN`, or through the optional `APE_ESCAPE_DISC_URL` secret. CI converts and verifies the disc in temporary storage; the CHD, CUE/BIN, boot executable and generated game translation are not committed or attached to releases.

Useful project files:

- `game.toml` — game identity and runtime/recompiler/video/controller configuration.
- `mods/preloaded/` — built-in optional features shown in the launcher.
- `src/mods/` — trusted native plugin code for the game's features.
- `ISSUES.md` — known behavior and reverse-engineering tasks.
- `docs/AOT_OVERLAYS.md` — notes on ahead-of-time archive overlay support.

## Credits and legal

This nvd123-maintained project uses the [PSXRecomp framework](https://github.com/mstan/psxrecomp) and other open-source components; their notices and licenses remain with the corresponding source and release files. The Quick Gadget Select package retains its original contributor credit in its manifest.

**Ape Escape** and its original game code, art, audio and other content are the property of Sony Computer Entertainment / Sony Interactive Entertainment. This repository and its releases do not include the original disc image or a retail PlayStation BIOS. Use only game and BIOS files you are legally entitled to use. This project is unofficial and is not affiliated with Sony.
