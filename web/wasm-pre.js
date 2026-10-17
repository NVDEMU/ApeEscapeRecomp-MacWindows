/* Emscripten pre-run hook; user game data stays in browser-local storage. */
if (typeof Module !== "undefined") {
  Module.preRun = Module.preRun || [];
  Module.preRun.push(function () {
    if (!Module.apeEscapeDiscBytes || Module.apeEscapeDiscBytes.byteLength === 0) {
      throw new Error("No Ape Escape disc image was passed to the WebAssembly runtime.");
    }
    if (!Module.apeEscapeBiosBytes || Module.apeEscapeBiosBytes.byteLength !== 512 * 1024) {
      throw new Error("This build requires a user-supplied 512 KiB SCPH-1001 BIOS dump.");
    }
    if (!FS.analyzePath("/game").exists) FS.mkdir("/game");
    FS.writeFile("/game/Ape Escape USA.chd", Module.apeEscapeDiscBytes);
    Module.apeEscapeDiscBytes = null;
    if (!FS.analyzePath("/bios").exists) FS.mkdir("/bios");
    FS.writeFile("/bios/SCPH1001.BIN", Module.apeEscapeBiosBytes);
    Module.apeEscapeBiosBytes = null;
    if (!FS.analyzePath("/saves").exists) FS.mkdir("/saves");
    try {
      FS.mount(IDBFS, {}, "/saves");
      addRunDependency("ape-escape-idbfs");
      FS.syncfs(true, function (error) {
        if (error && Module.printErr) Module.printErr("Save storage restore failed: " + error);
        removeRunDependency("ape-escape-idbfs");
      });
      const syncSaves = function () {
        try { FS.syncfs(false, function (error) { if (error && Module.printErr) Module.printErr("Save storage sync failed: " + error); }); }
        catch (error) { if (Module.printErr) Module.printErr("Save storage sync failed: " + error); }
      };
      const previousOnExit = Module.onExit;
      Module.onExit = function (code) { syncSaves(); if (typeof previousOnExit === "function") previousOnExit(code); };
      if (typeof window !== "undefined") {
        window.addEventListener("pagehide", syncSaves);
        document.addEventListener("visibilitychange", function () {
          if (document.visibilityState === "hidden") syncSaves();
        });
      }
    } catch (error) {
      if (Module.printErr) Module.printErr("Persistent browser saves unavailable; continuing with temporary saves. " + error);
    }
  });
}