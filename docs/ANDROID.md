# Experimental Android build

Ape Escape Recompiled - Enhanced Edition has an **experimental Android ARM64 APK target**. The Android app is separate from desktop packaging and uses the pinned SDL3/PSXRecomp sources.

## Current MVP

- ARM64 (`arm64-v8a`) debug APK built by `.github/workflows/android.yml`.
- Android setup screen imports a user-provided **Ape Escape USA .chd** into the app's game-data area.
- Uses the existing SDL game-controller input path; a paired Bluetooth or USB controller is recommended because Ape Escape depends on both analog sticks.
- Uses conservative software rendering at native PS1 resolution while platform graphics support is validated.
- Uses app-private writable storage for configuration and saves.
- Bundles the project's redistributable OpenBIOS image and its license notice.
- The GitHub Actions build retrieves the commercial game image privately for code generation only; the CHD is kept in temporary runner storage and is not included in the APK.

## Build locally

Install JDK 17, Android SDK API 35, Android NDK `28.2.13676358`, CMake `3.22.1`, and Gradle `8.9`. Then run the equivalent of the CI steps:

```sh
cmake -S psxrecomp-v4/recompiler -B psxrecomp-v4/recompiler/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build psxrecomp-v4/recompiler/build --parallel 2 --target psxrecomp-game psxrecomp-bios
(cd psxrecomp-v4 && bash tools/regen_bios.sh --config bios/OpenBIOS.toml)
gradle --no-daemon --max-workers=2 -p android :app:assembleDebug
```

The Android build applies a small idempotent patch to the pinned framework at configure time: Android loads a shared native library instead of a desktop executable, and the working directory is set to SDL's app-private files directory. This patch is guarded by `ANDROID` and does not run for Windows/macOS/Linux builds.

## Current limitations

- This is an early test build, not a release-grade Android product.
- The setup screen currently accepts CHD only. CUE/BIN multi-file imports are not implemented.
- A physical controller is the intended first control method; on-screen virtual DualShock controls are not implemented.
- The software renderer/native-resolution combination is a conservative initial profile. Device performance and audio latency still need testing on real hardware.
- Android netplay, touch controls, signed distribution builds, and automatic updating are not enabled.

The APK workflow uploads a build artifact only; it does not publish Android APKs to the desktop Nightly release until device testing and packaging are stable.
