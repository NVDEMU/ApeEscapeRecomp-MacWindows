#include "mod_packages.h"
#include "mod_media.h"

#include <filesystem>
#include <iostream>
#include <string>

namespace fs = std::filesystem;

// These bundled packages contain no donor media. Fail explicitly if a fixture
// unexpectedly starts depending on it, rather than opening external game data.
namespace PSXRecompV4 {
bool load_mod_media(const fs::path&, const std::string&, uint64_t,
                    const std::string&,
                    std::shared_ptr<const std::vector<uint8_t>>&,
                    std::string* error) {
    if (error) *error = "donor media is outside this catalog test";
    return false;
}
}

namespace {

constexpr const char* kGameId = "SCUS-94423";
constexpr const char* kDiscSha256 =
    "1ae17e78ebb8c782c7c1785b0a0bd7b0ee28235b8a0c83c8df887129899a852a";

int fail(const std::string& message) {
    std::cerr << "FAIL: " << message << "\n";
    return 1;
}

void no_op_plugin() {}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) return fail("expected the preloaded mods root");

    const fs::path source(argv[1]);
    const fs::path root =
        fs::temp_directory_path() / "apeescape-preloaded-mods-test";
    std::error_code ec;
    fs::remove_all(root, ec);
    fs::copy(source, root, fs::copy_options::recursive);

    size_t manifest_count = 0;
    for (const fs::directory_entry& entry :
         fs::recursive_directory_iterator(root / "packages")) {
        if (!entry.is_regular_file() ||
            entry.path().filename() != "manifest.toml") {
            continue;
        }
        ++manifest_count;
        PSXRecompV4::ModPackage package;
        std::string error;
        if (!PSXRecompV4::ModPackageManager::read_manifest(
                entry.path(), package, &error)) {
            return fail("manifest parse failed: " + error);
        }
    }
    if (manifest_count != 11) return fail("expected eleven package manifests");

    PSXRecompV4::mod_clear_plugins_for_tests();
    for (const char* id : {
             "ape.widescreen.16-9",
             "ape.widescreen.21-9",
             "ape.widescreen.adaptive",
             "ape.frame-smoothing.60",
             "ape.frame-smoothing.90",
             "ape.frame-smoothing.120",
             "ape.frame-smoothing.144",
             "ape.frame-smoothing.165",
             "ape.frame-smoothing.240",
             "ape.frame-smoothing.display",
             "ape.fmv.skip",
             "ape.gadgets.quick-select",
             "ape.gadgets.sky-flyer-triple-jump",
             "psx.pgxp",
             "ape.assist.infinite-lives",
             "ape.assist.infinite-health",
             "ape.assist.infinite-air",
             "ape.assist.all-gadgets",
             "ape.draw-distance.extended",
             "ape.qol.quick-retry",
             "ape.qol.camera-sensitivity",
             "ape.qol.collectible-stats",
             "ape.qol.enhanced-radar",
             "ape.qol.speedrun-timer",
             "ape.challenge.time-trial",
             "ape.challenge.no-damage",
             "ape.challenge.limited-lives",
             "ape.challenge.random-challenge",
             "ape.challenge.monkey-mayhem",
             "ape.challenge.nightmare-mode"}) {
        if (!PSXRecompV4::mod_register_activation_plugin(id, no_op_plugin))
            return fail(std::string("could not register test plugin ") + id);
    }

    PSXRecompV4::ModPackageManager manager(root);
    std::string error;
    if (!manager.scan(&error)) return fail("catalog scan failed: " + error);
    if (!manager.load_state(&error)) return fail("default state failed: " + error);
    if (manager.packages().size() != 11)
        return fail("expected ten package families");

    const auto default_plan = manager.resolve(kGameId, "", kDiscSha256);
    if (!default_plan.ok || !default_plan.writes.empty() ||
        !default_plan.plugins.empty()) {
        return fail("a mod feature was enabled by default");
    }

    // Every Quality-of-Life feature resolves independently and is default-off.
    for (const auto& [feature, plugin] :
         {std::pair{"quick-retry", "ape.qol.quick-retry"},
          std::pair{"camera-sensitivity", "ape.qol.camera-sensitivity"},
          std::pair{"collectible-stats", "ape.qol.collectible-stats"},
          std::pair{"enhanced-radar", "ape.qol.enhanced-radar"},
          std::pair{"speedrun-timer", "ape.qol.speedrun-timer"}}) {
        if (!manager.set_feature_enabled(
                "ape.enhancement.qol-tools", feature, true, &error)) {
            return fail(error);
        }
        const auto enabled_plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!enabled_plan.ok || !enabled_plan.writes.empty() ||
            enabled_plan.plugins.size() != 1 ||
            enabled_plan.plugins.front().id != plugin) {
            return fail(std::string("wrong QoL plugin plan for ") + feature);
        }
        if (!manager.set_feature_enabled(
                "ape.enhancement.qol-tools", feature, false, &error)) {
            return fail(error);
        }
        const auto disabled_plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!disabled_plan.ok || !disabled_plan.plugins.empty() ||
            !disabled_plan.writes.empty()) {
            return fail(std::string("QoL feature remained active after disabling ") +
                        feature);
        }
    }

    if (!manager.set_feature_enabled(
            "ape.enhancement.qol-tools", "camera-sensitivity", true, &error)) {
        return fail(error);
    }
    for (const char* choice : {"25", "50", "75", "100"}) {
        if (!manager.set_feature_option(
                "ape.enhancement.qol-tools", "camera-sensitivity",
                "sensitivity", choice, &error)) {
            return fail(error);
        }
        const auto sensitivity_plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!sensitivity_plan.ok || sensitivity_plan.plugins.size() != 1 ||
            sensitivity_plan.plugins.front().id != "ape.qol.camera-sensitivity") {
            return fail(std::string("wrong camera sensitivity plugin for ") + choice);
        }
    }
    if (!manager.set_feature_enabled(
            "ape.enhancement.qol-tools", "camera-sensitivity", false, &error)) {
        return fail(error);
    }


    // Every Gameplay Assist is a separate, default-off launcher feature.
    for (const auto& [feature, plugin] :
         {std::pair{"infinite-lives", "ape.assist.infinite-lives"},
          std::pair{"infinite-health", "ape.assist.infinite-health"},
          std::pair{"infinite-air", "ape.assist.infinite-air"},
          std::pair{"all-gadgets", "ape.assist.all-gadgets"}}) {
        if (!manager.set_feature_enabled(
                "ape.enhancement.gameplay-assists", feature, true, &error)) {
            return fail(error);
        }
        const auto assist_plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!assist_plan.ok || !assist_plan.writes.empty() ||
            assist_plan.plugins.size() != 1 ||
            assist_plan.plugins.front().id != plugin) {
            return fail(std::string("wrong Gameplay Assist plugin for ") + feature);
        }
        if (!manager.set_feature_enabled(
                "ape.enhancement.gameplay-assists", feature, false, &error)) {
            return fail(error);
        }
        const auto off_plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!off_plan.ok || !off_plan.plugins.empty() ||
            !off_plan.writes.empty()) {
            return fail(std::string("Gameplay Assist remained active after disabling ") +
                        feature);
        }
    }

    // Extended Draw Distance is a separate, default-off feature.
    if (!manager.set_feature_enabled(
            "ape.enhancement.extended-draw-distance", "extended-draw-distance",
            true, &error)) {
        return fail(error);
    }
    {
        const auto plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!plan.ok || !plan.writes.empty() || plan.plugins.size() != 1 ||
            plan.plugins.front().id != "ape.draw-distance.extended") {
            return fail("wrong Extended Draw Distance plugin plan");
        }
    }
    if (!manager.set_feature_enabled(
            "ape.enhancement.extended-draw-distance", "extended-draw-distance",
            false, &error)) {
        return fail(error);
    }
    {
        const auto plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!plan.ok || !plan.plugins.empty() || !plan.writes.empty()) {
            return fail("Extended Draw Distance remained active after disabling");
        }
    }

    if (!manager.set_feature_enabled(
            "ape.enhancement.widescreen", "widescreen", true, &error)) {
        return fail(error);
    }
    for (const auto& [choice, plugin] :
         {std::pair{"16:9", "ape.widescreen.16-9"},
          std::pair{"21:9", "ape.widescreen.21-9"},
          std::pair{"adaptive", "ape.widescreen.adaptive"}}) {
        if (!manager.set_feature_option(
                "ape.enhancement.widescreen", "widescreen",
                "aspect", choice, &error)) {
            return fail(error);
        }
        const auto plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!plan.ok || plan.plugins.size() != 1 ||
            plan.plugins.front().id != plugin) {
            return fail(std::string("wrong widescreen plugin for ") + choice);
        }
    }

    if (!manager.set_feature_enabled(
            "ape.enhancement.widescreen", "widescreen", false, &error) ||
        !manager.set_feature_enabled(
            "ape.enhancement.frame-smoothing", "temporal-blending", true, &error)) {
        return fail(error);
    }
    for (const auto& [choice, plugin] :
         {std::pair{"60", "ape.frame-smoothing.60"},
          std::pair{"90", "ape.frame-smoothing.90"},
          std::pair{"120", "ape.frame-smoothing.120"},
          std::pair{"144", "ape.frame-smoothing.144"},
          std::pair{"165", "ape.frame-smoothing.165"},
          std::pair{"240", "ape.frame-smoothing.240"},
          std::pair{"display", "ape.frame-smoothing.display"}}) {
        if (!manager.set_feature_option(
                "ape.enhancement.frame-smoothing", "temporal-blending",
                "rate", choice, &error)) {
            return fail(error);
        }
        const auto fps_plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!fps_plan.ok || !fps_plan.writes.empty() ||
            fps_plan.plugins.size() != 1 ||
            fps_plan.plugins.front().id != plugin) {
            return fail(std::string("wrong interpolated frame-rate plan for ") +
                        choice);
        }
    }
    if (!manager.set_feature_enabled(
            "ape.enhancement.frame-smoothing", "temporal-blending", false, &error) ||
        !manager.set_feature_enabled(
            "ape.enhancement.quick-gadget-select", "quick-gadget-select",
            true, &error)) {
        return fail(error);
    }

    /*
     * Quick Gadget Select is one vblank plugin plus one main_exe instruction
     * patch. That patch has to be a declarative write rather than a
     * psx_mod_write_code_word() from an activation callback: activation runs
     * before the guest boots, so the game's own EXE load would overwrite it.
     * Asserting the write is planned is what tells the two apart -- a
     * plugin-count assertion passes either way while the patch does nothing.
     */
    const auto quick_select_plan = manager.resolve(kGameId, "", kDiscSha256);
    if (!quick_select_plan.ok || quick_select_plan.plugins.size() != 1 ||
        quick_select_plan.plugins.front().id != "ape.gadgets.quick-select") {
        return fail("wrong Quick Gadget Select plugin plan");
    }
    if (quick_select_plan.writes.size() != 1)
        return fail("Quick Gadget Select did not plan its guest-code patch");
    {
        const auto& write = quick_select_plan.writes.front();
        const std::vector<uint8_t> expected{0xD2, 0xC2, 0x43, 0x80};
        const std::vector<uint8_t> replacement{0x7C, 0x8F, 0x01, 0x08};
        if (write.target != PSXRecompV4::ModPatchTarget::MainExe ||
            write.location != 0x80063B6Cull || write.expected != expected ||
            write.replacement != replacement) {
            return fail("wrong Quick Gadget Select guest-code patch");
        }
    }

    if (!manager.set_feature_enabled(
            "ape.enhancement.quick-gadget-select", "quick-gadget-select",
            false, &error)) {
        return fail(error);
    }
    const auto disabled_plan = manager.resolve(kGameId, "", kDiscSha256);
    if (!disabled_plan.ok || !disabled_plan.writes.empty())
        return fail("Quick Gadget Select patched guest code while disabled");

    // Sky Flyer Triple Jump is a separate, default-off controller enhancement.
    if (!manager.set_feature_enabled(
            "ape.enhancement.sky-flyer-triple-jump", "sky-flyer-triple-jump",
            true, &error)) {
        return fail(error);
    }
    {
        const auto sky_flyer_plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!sky_flyer_plan.ok || !sky_flyer_plan.writes.empty() ||
            sky_flyer_plan.plugins.size() != 1 ||
            sky_flyer_plan.plugins.front().id != "ape.gadgets.sky-flyer-triple-jump") {
            return fail("wrong Sky Flyer Triple Jump plugin plan");
        }
    }
    if (!manager.set_feature_enabled(
            "ape.enhancement.sky-flyer-triple-jump", "sky-flyer-triple-jump",
            false, &error)) {
        return fail(error);
    }
    {
        const auto sky_flyer_off_plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!sky_flyer_off_plan.ok || !sky_flyer_off_plan.plugins.empty() ||
            !sky_flyer_off_plan.writes.empty()) {
            return fail("Sky Flyer Triple Jump remained active after disabling");
        }
    }

    // Challenge Pack features are independent, default-off and select the
    // expected native plugin only when explicitly enabled.
    for (const auto& [feature, plugin] :
         {std::pair{"time-trial", "ape.challenge.time-trial"},
          std::pair{"no-damage", "ape.challenge.no-damage"},
          std::pair{"limited-lives", "ape.challenge.limited-lives"},
          std::pair{"random-challenge", "ape.challenge.random-challenge"}}) {
        if (!manager.set_feature_enabled(
                "ape.enhancement.challenge-pack", feature, true, &error)) {
            return fail(error);
        }
        const auto challenge_plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!challenge_plan.ok || !challenge_plan.writes.empty() ||
            challenge_plan.plugins.size() != 1 ||
            challenge_plan.plugins.front().id != plugin) {
            return fail(std::string("wrong Challenge Pack plugin plan for ") + feature);
        }
        if (!manager.set_feature_enabled(
                "ape.enhancement.challenge-pack", feature, false, &error)) {
            return fail(error);
        }
        const auto challenge_off_plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!challenge_off_plan.ok || !challenge_off_plan.plugins.empty() ||
            !challenge_off_plan.writes.empty()) {
            return fail(std::string("Challenge Pack feature remained active: ") + feature);
        }
    }

    // Hardcore rules live in a separate package, keeping the regular Challenge Pack's
    // four native plugin mappings independent of the runtime catalog's existing limit.
    for (const auto& [feature, plugin] :
         {std::pair{"monkey-mayhem", "ape.challenge.monkey-mayhem"},
          std::pair{"nightmare-mode", "ape.challenge.nightmare-mode"}}) {
        if (!manager.set_feature_enabled(
                "ape.enhancement.hardcore-challenges", feature, true, &error)) {
            return fail(error);
        }
        const auto hardcore_plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!hardcore_plan.ok || !hardcore_plan.writes.empty() ||
            hardcore_plan.plugins.size() != 1 ||
            hardcore_plan.plugins.front().id != plugin) {
            return fail(std::string("wrong Hardcore Challenges plugin plan for ") + feature);
        }
        if (!manager.set_feature_enabled(
                "ape.enhancement.hardcore-challenges", feature, false, &error)) {
            return fail(error);
        }
        const auto hardcore_off_plan = manager.resolve(kGameId, "", kDiscSha256);
        if (!hardcore_off_plan.ok || !hardcore_off_plan.plugins.empty() ||
            !hardcore_off_plan.writes.empty()) {
            return fail(std::string("Hardcore Challenge remained active: ") + feature);
        }
    }

    if (!manager.set_feature_enabled(
            "ape.enhancement.challenge-pack", "time-trial", true, &error) ||
        !manager.set_feature_enabled(
            "ape.enhancement.challenge-pack", "limited-lives", true, &error) ||
        !manager.set_feature_enabled(
            "ape.enhancement.challenge-pack", "random-challenge", true, &error)) {
        return fail(error);
    }
    for (const char* choice : {"180", "300", "600"}) {
        if (!manager.set_feature_option(
                "ape.enhancement.challenge-pack", "time-trial",
                "time-limit", choice, &error) ||
            !manager.set_feature_option(
                "ape.enhancement.challenge-pack", "random-challenge",
                "time-limit", choice, &error)) {
            return fail(error);
        }
    }
    for (const char* choice : {"1", "3", "5"}) {
        if (!manager.set_feature_option(
                "ape.enhancement.challenge-pack", "limited-lives",
                "starting-lives", choice, &error) ||
            !manager.set_feature_option(
                "ape.enhancement.challenge-pack", "random-challenge",
                "starting-lives", choice, &error)) {
            return fail(error);
        }
    }
    for (const char* feature : {"time-trial", "limited-lives", "random-challenge"}) {
        if (!manager.set_feature_enabled(
                "ape.enhancement.challenge-pack", feature, false, &error)) {
            return fail(error);
        }
    }

    fs::remove_all(root, ec);
    std::cout << "Ape Escape preloaded mods: 11 packages, every feature default-off, "
                 "3 widescreen choices, 7 interpolated frame-rate choices, "
                 "four independent Gameplay Assist toggles, Extended Draw Distance opt-in, "
                 "Quick Gadget Select guarded patch, five QoL features, four Challenge Pack features/options and two Hardcore Challenge features\n";
    return 0;
}
