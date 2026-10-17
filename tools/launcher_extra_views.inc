/* APE_ESCAPE_NEW_FEATURES_HELPER
 * Launcher-side features. Challenge data and profile data stay in the user's
 * data directory; no game RAM is modified by these tools.
 */
static std::string s_ape_daily_status;
static std::string s_ape_save_protection_status;
static std::string s_ape_toolkit_status;
static int s_ape_stage_selected = 0;
static bool s_ape_stage_show_tips = true;

static bool ape_escape_copy_regular_tree(const std::filesystem::path& source,
                                         const std::filesystem::path& target,
                                         bool skip_save_protection = false) {
    std::error_code ec;
    if (!std::filesystem::exists(source, ec)) return !ec;
    if (ec || !std::filesystem::is_directory(source, ec) || ec) return false;
    std::filesystem::create_directories(target, ec);
    if (ec) return false;
    for (std::filesystem::directory_iterator it(source, ec), end; !ec && it != end; it.increment(ec)) {
        const auto status = it->symlink_status(ec);
        if (ec) return false;
        if (std::filesystem::is_symlink(status)) continue;
        const auto name = it->path().filename();
        if (skip_save_protection && name == "save-protection" &&
            std::filesystem::is_directory(status)) continue;
        const auto destination = target / name;
        if (std::filesystem::is_directory(status)) {
            if (!ape_escape_copy_regular_tree(it->path(), destination, false)) return false;
        } else if (std::filesystem::is_regular_file(status)) {
            std::filesystem::create_directories(destination.parent_path(), ec);
            if (ec) return false;
            std::filesystem::copy_file(it->path(), destination,
                std::filesystem::copy_options::overwrite_existing, ec);
            if (ec) return false;
        }
    }
    return !ec;
}

static std::string ape_escape_backup_timestamp() {
    const std::time_t now = std::time(nullptr);
    const std::tm* local = std::localtime(&now);
    char stamp[32] = {};
    if (!local || std::strftime(stamp, sizeof(stamp), "%Y%m%d-%H%M%S", local) == 0)
        return {};
    return stamp;
}

static std::filesystem::path ape_escape_latest_save_backup() {
    const auto root = ape_escape_data_directory() / "save-protection";
    std::error_code ec;
    if (!std::filesystem::is_directory(root, ec) || ec) return {};
    std::filesystem::path latest;
    std::string latest_name;
    for (std::filesystem::directory_iterator it(root, ec), end; !ec && it != end; it.increment(ec)) {
        if (!it->is_directory(ec) || ec) { ec.clear(); continue; }
        const std::string name = it->path().filename().string();
        if (name.rfind("backup-", 0) != 0) continue;
        ec.clear();
        if (!std::filesystem::is_regular_file(it->path() / "BACKUP_INFO.txt", ec) || ec) {
            ec.clear();
            continue;
        }
        if (name > latest_name) {
            latest_name = name;
            latest = it->path();
        }
    }
    return latest;
}

static void ape_escape_prune_save_backups() {
    const auto root = ape_escape_data_directory() / "save-protection";
    std::error_code ec;
    for (;;) {
        std::map<std::string, std::filesystem::path> backups;
        ec.clear();
        if (!std::filesystem::is_directory(root, ec) || ec) return;
        for (std::filesystem::directory_iterator it(root, ec), end; !ec && it != end; it.increment(ec)) {
            const std::string name = it->path().filename().string();
            if (name.rfind("backup-", 0) != 0) continue;
            ec.clear();
            if (!it->is_directory(ec) || ec) { ec.clear(); continue; }
            if (std::filesystem::is_regular_file(it->path() / "BACKUP_INFO.txt", ec) && !ec)
                backups.emplace(name, it->path());
            ec.clear();
        }
        if (ec || backups.size() <= 20u) return;
        ec.clear();
        std::filesystem::remove_all(backups.begin()->second, ec);
        if (ec) return;
    }
}

static std::filesystem::path ape_escape_create_save_backup() {
    const auto data = ape_escape_data_directory();
    const auto app = ape_escape_application_directory();
    const auto root = data / "save-protection";
    std::error_code ec;
    std::filesystem::create_directories(root, ec);
    if (ec) return {};
    const std::string stamp = ape_escape_backup_timestamp();
    if (stamp.empty()) return {};
    std::string suffix;
    std::filesystem::path target;
    for (unsigned attempt = 0; attempt < 100; ++attempt) {
        suffix = attempt == 0 ? "" : "-" + std::to_string(attempt);
        target = root / ("backup-" + stamp + suffix);
        ec.clear();
        if (!std::filesystem::exists(target, ec) && !ec) break;
        target.clear();
    }
    if (target.empty()) return {};
    const auto pending = root / (".pending-" + stamp + suffix);
    std::filesystem::remove_all(pending, ec);
    ec.clear();
    std::filesystem::create_directories(pending, ec);
    if (ec) return {};
    const bool user_ok = ape_escape_copy_regular_tree(data, pending / "user-data", true);
    const bool saves_ok = ape_escape_copy_regular_tree(app / "saves", pending / "app-saves", false);
    if (!user_ok || !saves_ok) {
        std::filesystem::remove_all(pending, ec);
        return {};
    }
    std::ofstream info(pending / "BACKUP_INFO.txt", std::ios::trunc);
    if (!info) {
        std::filesystem::remove_all(pending, ec);
        return {};
    }
    info << "Ape Escape Recompiled - Enhanced Edition save protection backup\n"
         << "Created: " << stamp << "\n"
         << "Contents: user-writable application data and the install-local saves/ folder when present\n"
         << "Restore mode: merges snapshot files; files not present in the snapshot are not deleted.\n";
    info.close();
    if (!info) {
        std::filesystem::remove_all(pending, ec);
        return {};
    }
    std::filesystem::rename(pending, target, ec);
    if (ec) {
        std::filesystem::remove_all(pending, ec);
        return {};
    }
    ape_escape_prune_save_backups();
    return target;
}

static bool ape_escape_restore_save_backup(const std::filesystem::path& snapshot) {
    if (snapshot.empty() ||
        !std::filesystem::is_regular_file(snapshot / "BACKUP_INFO.txt")) return false;
    /* Preserve the current state before applying an older snapshot. */
    if (ape_escape_create_save_backup().empty()) return false;
    const bool data_ok = ape_escape_copy_regular_tree(
        snapshot / "user-data", ape_escape_data_directory(), false);
    const bool saves_ok = ape_escape_copy_regular_tree(
        snapshot / "app-saves", ape_escape_application_directory() / "saves", false);
    return data_ok && saves_ok;
}

/* SAVE PROTECTION CENTER is explicit/manual. Restore is confirmed in the UI,
 * first creates a safety backup, merges files, and never deletes newer files. */
static void ape_escape_draw_save_protection_center(const LauncherTheme& th,
                                                    float button_w, float gap) {
    ImGui::Spacing();
    ImGui::Separator();
    ImGui::TextColored(col(th.accent2), "SAVE PROTECTION CENTER");
    ImGui::TextWrapped("Back up user data and the install-local saves/ folder when present. Restore makes a safety backup first and does not delete files absent from the selected snapshot.");
    const auto latest = ape_escape_latest_save_backup();
    if (ImGui::Button("Create Backup Now", ImVec2(button_w, px(34.0f)))) {
        const auto created = ape_escape_create_save_backup();
        s_ape_save_protection_status = created.empty()
            ? "Backup failed. Check disk permissions and available storage."
            : "Backup created: " + created.filename().string();
    }
    ImGui::SameLine(0, gap);
    if (latest.empty()) ImGui::BeginDisabled();
    if (ImGui::Button("Restore Latest Backup", ImVec2(button_w, px(34.0f))))
        ImGui::OpenPopup("Confirm Save Restore");
    if (latest.empty()) {
        ImGui::EndDisabled();
        ImGui::TextDisabled("No valid backup exists yet. Create one before restoring.");
    } else {
        ImGui::TextWrapped("Latest snapshot: %s", latest.filename().string().c_str());
    }
    if (ImGui::BeginPopupModal("Confirm Save Restore", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::TextWrapped("The current files will be backed up first. Matching files will then be overwritten by the latest snapshot; newer files will not be deleted.");
        if (ImGui::Button("Create Safety Backup and Restore", ImVec2(px(270.0f), px(34.0f)))) {
            s_ape_save_protection_status = ape_escape_restore_save_backup(latest)
                ? "Restore completed. A pre-restore safety snapshot was saved."
                : "Restore failed. Check permissions and backup integrity.";
            ImGui::CloseCurrentPopup();
        }
        ImGui::SameLine();
        if (ImGui::Button("Cancel", ImVec2(px(100.0f), px(34.0f))))
            ImGui::CloseCurrentPopup();
        ImGui::EndPopup();
    }
    if (!s_ape_save_protection_status.empty())
        ImGui::TextWrapped("%s", s_ape_save_protection_status.c_str());
}

/* A date-only deterministic challenge seed: no network, no game RNG, no uploads. */
struct ApeEscapeDailyChallenge {
    std::string date, code, first, second;
};
static std::map<std::string, bool> ape_escape_load_daily_history() {
    std::map<std::string, bool> history;
    std::ifstream in(ape_escape_data_directory() / "ape_escape_daily_challenges.tsv");
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream row(line);
        std::string date, code, complete;
        if (std::getline(row, date, '\t') && std::getline(row, code, '\t') &&
            std::getline(row, complete) && !date.empty())
            history[date] = complete == "1";
    }
    return history;
}
static bool ape_escape_save_daily_history(const std::map<std::string, bool>& history) {
    const auto path = ape_escape_data_directory() / "ape_escape_daily_challenges.tsv";
    std::ofstream out(path, std::ios::trunc);
    if (!out) return false;
    out << "# date<TAB>daily-code<TAB>manually-marked-complete\n";
    for (const auto& record : history)
        out << record.first << '\t' << "AE-" << record.first << '\t'
            << (record.second ? "1" : "0") << '\n';
    out.close();
    return static_cast<bool>(out);
}
static uint32_t ape_escape_daily_next(uint32_t* state) {
    *state ^= *state << 13u;
    *state ^= *state >> 17u;
    *state ^= *state << 5u;
    if (*state == 0u) *state = 0xA341316Cu;
    return *state;
}
static std::string ape_escape_daily_rule(unsigned kind, uint32_t* state) {
    if (kind == 0u) {
        const unsigned minutes[] = {3u, 5u, 10u};
        return "Timed Monkey Hunt — " + std::to_string(minutes[ape_escape_daily_next(state) % 3u]) + " minutes";
    }
    if (kind == 1u) return "No-Damage Run — finish without losing health";
    const unsigned lives[] = {1u, 3u, 5u};
    return "Limited Lives — " + std::to_string(lives[ape_escape_daily_next(state) % 3u]) + " starting lives";
}
static ApeEscapeDailyChallenge ape_escape_today_challenge() {
    const std::time_t now = std::time(nullptr);
    const std::tm* local = std::localtime(&now);
    std::tm date_parts{};
    if (local) date_parts = *local;
    char date[16] = {};
    std::strftime(date, sizeof(date), "%Y-%m-%d", &date_parts);
    const uint32_t numeric_date = static_cast<uint32_t>((date_parts.tm_year + 1900) * 10000 +
        (date_parts.tm_mon + 1) * 100 + date_parts.tm_mday);
    uint32_t state = numeric_date ^ 0x9E3779B9u;
    if (!state) state = 0xA341316Cu;
    const unsigned first_kind = ape_escape_daily_next(&state) % 3u;
    unsigned second_kind = ape_escape_daily_next(&state) % 3u;
    if (second_kind == first_kind) second_kind = (second_kind + 1u) % 3u;
    const uint32_t code_value = ape_escape_daily_next(&state) & 0xFFFFu;
    char code[40] = {};
    std::snprintf(code, sizeof(code), "AE-%04d%02d%02d-%04X",
        date_parts.tm_year + 1900, date_parts.tm_mon + 1, date_parts.tm_mday,
        static_cast<unsigned>(code_value));
    return {date, code, ape_escape_daily_rule(first_kind, &state),
            ape_escape_daily_rule(second_kind, &state)};
}
static void ape_escape_draw_daily_challenge(LauncherModel*, const LauncherTheme& th) {
    const auto challenge = ape_escape_today_challenge();
    auto history = ape_escape_load_daily_history();
    const bool completed = history[challenge.date];
    ImGui::TextColored(col(th.accent2), "DAILY CHALLENGE");
    ImGui::TextWrapped("A reproducible challenge generated from your local calendar date. Players using the same date and version receive the same rules.");
    ImGui::Separator();
    ImGui::Text("Date: %s", challenge.date.c_str());
    ImGui::TextColored(col(th.accent), "Challenge code: %s", challenge.code.c_str());
    ImGui::Spacing();
    ImGui::BulletText("Primary rule: %s", challenge.first.c_str());
    ImGui::BulletText("Bonus rule: %s", challenge.second.c_str());
    ImGui::TextDisabled("Enable matching Challenge Pack features in Mods yourself. Rules are not auto-enabled, gameplay results are not verified, and no scores are uploaded.");
    if (ImGui::Button("Copy Challenge Code", ImVec2(px(190.0f), px(32.0f)))) {
        ImGui::SetClipboardText(challenge.code.c_str());
        s_ape_daily_status = "Challenge code copied.";
    }
    ImGui::SameLine();
    if (!completed && ImGui::Button("Mark Complete", ImVec2(px(160.0f), px(32.0f)))) {
        history[challenge.date] = true;
        s_ape_daily_status = ape_escape_save_daily_history(history)
            ? "Completion recorded locally. Results are self-reported."
            : "Could not write the local challenge history.";
    } else if (completed && ImGui::Button("Undo Completion", ImVec2(px(160.0f), px(32.0f)))) {
        history[challenge.date] = false;
        s_ape_daily_status = ape_escape_save_daily_history(history)
            ? "Completion mark removed."
            : "Could not update the local challenge history.";
    }
    if (!s_ape_daily_status.empty()) ImGui::TextWrapped("%s", s_ape_daily_status.c_str());
    std::size_t completed_count = 0;
    for (const auto& item : history) if (item.second) ++completed_count;
    ImGui::Text("Recorded completed challenge dates: %u", static_cast<unsigned>(completed_count));
}

static const char* ape_escape_stage_tip(int id) {
    switch (id) {
        case 0: return "Open routes reward decisive pursuit. Observe the monkey's reaction, then close distance before switching to your capture gadget.";
        case 1: return "Plan around the environment before chasing an alerted target. A short, safe route is often better than blindly following a fleeing monkey.";
        case 2: return "Prioritize safe footing near environmental hazards. Check your direction before committing to a long chase.";
        case 10: return "Use the Radar when vegetation or terrain hides a target. Reposition before changing to a slower capture tool.";
        case 11: return "Check side paths and corners before leaving an area. Avoid letting an alerted monkey pull you away from unexplored routes.";
        case 12: return "Scout the nearby route before pursuing. If a monkey gains distance, use the Radar to reacquire it rather than guessing.";
        case 20: return "Open areas can favor quick pursuit. Keep control near edges and check the path ahead before committing to a chase.";
        case 21: return "In enclosed routes, make room to turn before using movement gadgets. Check nearby side passages when a target leaves view.";
        case 22: return "Work through the area in a deliberate loop to reduce backtracking. Check the Radar for targets you may have passed.";
        case 30: return "Keep a clear escape route during pursuit. If terrain blocks your view, pause and reacquire the target with the Radar.";
        case 31: return "Plan turns before building speed and avoid chasing blindly around corners. Re-check the surrounding route after a capture.";
        case 32: return "Watch the environment while pursuing monkeys. If the direct path is risky, reposition instead of continuing at full speed.";
        case 40: return "Use controlled approaches in narrow passages. Switch gadgets before a chase when possible to avoid losing time on menus.";
        case 41: return "Pay attention to changes in elevation and route layout. Reposition before using gadgets that need a clear path.";
        case 42: return "Check adjacent routes and keep track of your return path. A quick Radar check can prevent unnecessary backtracking.";
        case 50: return "Sweep the area in sections and check beyond your current line of sight. Keep track of branches you have not explored.";
        case 51: return "Treat machinery and environmental hazards as part of the route. Scout a safe approach before pursuing a fleeing monkey.";
        case 52: return "Look for elevation changes and safe places to turn around. Keep an eye on the Radar when a target leaves the screen.";
        case 60: return "Prepare your gadget loadout before starting, then clear the stage methodically. This is a general briefing, not a verified boss walkthrough.";
        default: return "Scout the route, check the Radar when a monkey leaves view, and switch gadgets before a long chase. These are general tips, not a live map.";
    }
}
static void ape_escape_draw_stage_guide(LauncherModel*, const LauncherTheme& th) {
    ape_escape_load_monke_catalog();
    std::map<int, std::string> stages;
    for (const auto& entry : s_ape_monke_entries) stages.emplace(entry.stage, entry.stage_name);
    if (stages.empty()) {
        ImGui::TextWrapped("Stage cards could not load because assets/monkepedia.tsv is missing.");
        return;
    }
    if (stages.find(s_ape_stage_selected) == stages.end()) s_ape_stage_selected = stages.begin()->first;
    ImGui::TextColored(col(th.accent2), "STAGE KNOWLEDGE CARDS");
    ImGui::TextWrapped("Stage briefings use the project's North-American monkey roster. Tips are general guidance, not live gameplay telemetry.");
    ImGui::BeginChild("ape_stage_card_picker", ImVec2(0, px(170.0f)), true);
    for (const auto& stage : stages) {
        const auto count = static_cast<unsigned>(std::count_if(
            s_ape_monke_entries.begin(), s_ape_monke_entries.end(),
            [&stage](const ApeMonkeEntry& entry) { return entry.stage == stage.first; }));
        const std::string label = stage.second + "  (" + std::to_string(count) + " listed monkeys)##stage_" + std::to_string(stage.first);
        if (ImGui::Selectable(label.c_str(), s_ape_stage_selected == stage.first))
            s_ape_stage_selected = stage.first;
    }
    ImGui::EndChild();
    ImGui::Spacing();
    ImGui::Separator();
    ImGui::TextColored(col(th.accent), "%s", stages[s_ape_stage_selected].c_str());
    const auto roster_count = static_cast<unsigned>(std::count_if(
        s_ape_monke_entries.begin(), s_ape_monke_entries.end(),
        [](const ApeMonkeEntry& entry) { return entry.stage == s_ape_stage_selected; }));
    ImGui::Text("Source-backed roster: %u listed monkeys", roster_count);
    ImGui::TextWrapped("Objective: capture the stage's monkeys and use the game's own completion indicators to confirm progress.");
    if (s_ape_stage_show_tips) ImGui::TextWrapped("Field note: %s", ape_escape_stage_tip(s_ape_stage_selected));
    ImGui::Checkbox("Show general gameplay tips", &s_ape_stage_show_tips);
    const auto found = std::find_if(s_ape_monke_entries.begin(), s_ape_monke_entries.end(),
        [](const ApeMonkeEntry& entry) { return entry.stage == s_ape_stage_selected; });
    if (found != s_ape_monke_entries.end() && !found->source_url.empty()) {
        ImGui::TextWrapped("Roster reference: %s", found->source_url.c_str());
        if (ImGui::Button("Open Roster Source", ImVec2(px(190.0f), px(32.0f)))) {
            if (!SDL_OpenURL(found->source_url.c_str()))
                s_ape_toolkit_status = "Could not open the stage's roster reference.";
        }
    }
}

static const char APE_ESCAPE_EXAMPLE_PLUGIN[] = R"APE_PLUGIN(#include "mod_plugins.h"
#include <stdint.h>

/* Read-only starter. Verify address semantics against the current game build. */
static void example_vblank(void) {
    if (!psx_mod_game_started()) return;
    const uint16_t observed_word = psx_mod_read_half(0x800F4490u);
    (void)observed_word;
}

PSX_MOD_CONSTRUCTOR(register_example_plugin) {
    (void)psx_mod_register_vblank_plugin("example.timer-observer", example_vblank);
}
)APE_PLUGIN";
static void ape_escape_draw_mod_toolkit(LauncherModel*, const LauncherTheme& th) {
    ImGui::TextColored(col(th.accent2), "MOD DEVELOPER TOOLKIT");
    ImGui::TextWrapped("Start from the documented project API and a read-only observer. Undocumented memory writes can break game state or softlock stages.");
    ImGui::Separator();
    ImGui::BulletText("Use a unique plugin ID and keep every feature disabled by default.");
    ImGui::BulletText("Guard callbacks to the correct gameplay phase and clear transient state at stage transitions.");
    ImGui::BulletText("Record evidence for RAM mappings. Compilation alone does not validate behavior in-game.");
    ImGui::BulletText("Keep user data separate from the app install and test on clean saves.");
    if (ImGui::Button("Copy Minimal Plugin Template", ImVec2(px(230.0f), px(34.0f)))) {
        ImGui::SetClipboardText(APE_ESCAPE_EXAMPLE_PLUGIN);
        s_ape_toolkit_status = "A read-only example plugin was copied to the clipboard.";
    }
    if (ImGui::Button("Open Mod Developer Documentation", ImVec2(px(260.0f), px(34.0f)))) {
        if (SDL_OpenURL("https://github.com/NVDEMU/ApeEscapeRecomp-MacWindowsLinux/blob/master/docs/MOD_DEVELOPER_TOOLKIT.md"))
            s_ape_toolkit_status = "Opened the project mod-development documentation.";
        else
            s_ape_toolkit_status = "Could not open the documentation URL.";
    }
    if (!s_ape_toolkit_status.empty()) ImGui::TextWrapped("%s", s_ape_toolkit_status.c_str());
}
