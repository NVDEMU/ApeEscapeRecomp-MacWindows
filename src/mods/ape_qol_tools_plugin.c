#include "mod_plugins.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

/* All five callbacks are opt-in through the bundled manifest. */
static const uint32_t PHASE = 0x800F447Cu;
static const uint32_t PAD_LOW = 0x800B87A2u;
static const uint32_t HEALTH = 0x800EC2C8u;
static const uint32_t LIVES = 0x800F448Cu;
static const uint32_t LEVEL_TIMER = 0x800F4490u;
static const uint32_t TRIANGLES = 0x800F44B8u;
static const uint32_t SPECTER_COINS = 0x800F44BAu;
static const uint32_t MONKEY_FLAGS = 0x80139368u;
static const uint32_t GP0 = 0x1F801810u;

enum {
    PHASE_PLAYING = 3u,
    SELECT_BUTTON = 0x01u,
    L3_BUTTON = 0x02u,
    R3_BUTTON = 0x04u,
    RETRY_CHORD = SELECT_BUTTON | L3_BUTTON | R3_BUTTON,
    DPAD_MASK = 0xF0u,
    MONKEY_COUNT = 20u
};

typedef struct ApeGlyph {
    char ch;
    uint8_t rows[7];
} ApeGlyph;

/* Compact uppercase/number font; lit pixels are opaque GP0 rectangles. */
static const ApeGlyph FONT[] = {
    {'A',{14,17,17,31,17,17,17}}, {'B',{30,17,17,30,17,17,30}},
    {'C',{14,17,16,16,16,17,14}}, {'D',{30,17,17,17,17,17,30}},
    {'E',{31,16,16,30,16,16,31}}, {'F',{31,16,16,30,16,16,16}},
    {'G',{14,17,16,23,17,17,15}}, {'H',{17,17,17,31,17,17,17}},
    {'I',{14,4,4,4,4,4,14}},      {'J',{7,2,2,2,18,18,12}},
    {'K',{17,18,20,24,20,18,17}}, {'L',{16,16,16,16,16,16,31}},
    {'M',{17,27,21,21,17,17,17}}, {'N',{17,25,25,21,19,19,17}},
    {'O',{14,17,17,17,17,17,14}}, {'P',{30,17,17,30,16,16,16}},
    {'Q',{14,17,17,17,21,18,13}}, {'R',{30,17,17,30,20,18,17}},
    {'S',{15,16,16,14,1,1,30}},   {'T',{31,4,4,4,4,4,4}},
    {'U',{17,17,17,17,17,17,14}}, {'V',{17,17,17,17,17,10,4}},
    {'W',{17,17,17,21,21,21,10}}, {'X',{17,17,10,4,10,17,17}},
    {'Y',{17,17,10,4,4,4,4}},     {'Z',{31,1,2,4,8,16,31}},
    {'0',{14,17,19,21,25,17,14}}, {'1',{4,12,4,4,4,4,14}},
    {'2',{14,17,1,2,4,8,31}},     {'3',{30,1,1,14,1,1,30}},
    {'4',{2,6,10,18,31,2,2}},     {'5',{31,16,16,30,1,1,30}},
    {'6',{14,16,16,30,17,17,14}}, {'7',{31,1,2,4,8,8,8}},
    {'8',{14,17,17,14,17,17,14}}, {'9',{14,17,17,15,1,1,14}},
    {':',{0,4,4,0,4,4,0}},        {'/',{1,2,2,4,8,8,16}},
    {'.',{0,0,0,0,0,12,12}},       {'-',{0,0,0,31,0,0,0}}
};

static uint32_t color(uint8_t r, uint8_t g, uint8_t b) {
    return (uint32_t)r | ((uint32_t)g << 8u) | ((uint32_t)b << 16u);
}

static void rect(int x, int y, int w, int h, uint32_t rgb) {
    if (w <= 0 || h <= 0 || x < -512 || y < -512 ||
        x > 2048 || y > 2048)
        return;
    psx_mod_write_word(GP0, 0x60000000u | rgb);
    psx_mod_write_word(GP0, ((uint32_t)(uint16_t)y << 16u) |
                             (uint32_t)(uint16_t)x);
    psx_mod_write_word(GP0, ((uint32_t)(uint16_t)h << 16u) |
                             (uint32_t)(uint16_t)w);
}

static uint8_t glyph_row(char ch, unsigned row) {
    size_t i;
    if (row >= 7u)
        return 0u;
    for (i = 0u; i < sizeof(FONT) / sizeof(FONT[0]); ++i)
        if (FONT[i].ch == ch)
            return FONT[i].rows[row];
    return 0u;
}

static void text(const char *s, int x, int y, uint32_t rgb) {
    if (s == NULL)
        return;
    for (; *s != '\0'; ++s, x += 6) {
        unsigned row;
        for (row = 0u; row < 7u; ++row) {
            const uint8_t bits = glyph_row(*s, row);
            int col = 0;
            while (col < 5) {
                int start;
                if ((bits & (uint8_t)(1u << (4 - col))) == 0u) {
                    ++col;
                    continue;
                }
                start = col;
                while (col < 5 &&
                       (bits & (uint8_t)(1u << (4 - col))) != 0u)
                    ++col;
                rect(x + start, y + (int)row, col - start, 1, rgb);
            }
        }
    }
}

static int gameplay_active(void) {
    return psx_mod_game_started() && psx_mod_read_byte(PHASE) == PHASE_PLAYING;
}

static unsigned caught_monkeys(void) {
    unsigned i;
    unsigned caught = 0u;
    for (i = 0u; i < MONKEY_COUNT; ++i)
        if (psx_mod_read_byte(MONKEY_FLAGS + i * 8u) == 1u)
            ++caught;
    return caught;
}

static void panel(int x, int y, int w, int h) {
    const uint32_t border = color(87u, 105u, 129u);
    rect(x, y, w, h, color(15u, 19u, 27u));
    rect(x, y, w, 1, border);
    rect(x, y + h - 1, w, 1, border);
    rect(x, y, 1, h, border);
    rect(x + w - 1, y, 1, h, border);
}

/*
 * Experimental fast respawn, not a full level-state reload. Select+L3+R3
 * triggers the game's normal death path and resets its displayed level timer.
 * It costs a life, requires at least two to avoid accidental game-over, and
 * does not reset enemy/collectible state. Button report is active-low.
 */
static uint8_t retry_latched;
static void quick_retry_vblank(void) {
    const uint8_t raw = psx_mod_read_byte(PAD_LOW);
    const int pressed = (((uint8_t)~raw & RETRY_CHORD) == RETRY_CHORD);
    if (!pressed) {
        retry_latched = 0u;
        return;
    }
    if (retry_latched || !gameplay_active())
        return;
    retry_latched = 1u;
    if (psx_mod_read_half(LIVES) < 2u) {
        psx_mod_counter_add("ape.qol.quick_retry.low_lives", 1u);
        return;
    }
    psx_mod_write_half(LEVEL_TIMER, 0u);
    psx_mod_write_half(HEALTH, 0u);
    psx_mod_counter_add("ape.qol.quick_retry.triggered", 1u);
}

/* D-pad camera input is filtered only in active play; analog axes and menus
 * are untouched. A lower percentage suppresses a fraction of D-pad frames. */
static unsigned camera_percent = 100u;
static unsigned camera_frame;
static void camera_sensitivity_activate(void) {
    char value[16] = {0};
    unsigned parsed;
    camera_percent = 100u;
    camera_frame = 0u;
    if (!psx_mod_option_value("ape.enhancement.qol-tools",
                              "camera-sensitivity", "sensitivity",
                              value, (uint32_t)sizeof(value)))
        return;
    parsed = (unsigned)strtoul(value, NULL, 10);
    if (parsed == 25u || parsed == 50u || parsed == 75u || parsed == 100u)
        camera_percent = parsed;
}

static void camera_sensitivity_vblank(void) {
    uint8_t raw;
    unsigned phase;
    int suppress = 0;
    if (!gameplay_active() || camera_percent >= 100u)
        return;
    ++camera_frame;
    raw = psx_mod_read_byte(PAD_LOW);
    phase = camera_frame % 4u;
    if (camera_percent == 25u)
        suppress = phase != 0u;
    else if (camera_percent == 50u)
        suppress = (camera_frame % 2u) == 0u;
    else if (camera_percent == 75u)
        suppress = phase == 0u;
    if (suppress)
        psx_mod_write_byte(PAD_LOW, (uint8_t)(raw | DPAD_MASK));
}

static void collectible_stats_vblank(void) {
    char line[32];
    const uint32_t display_h = psx_mod_display_height();
    const uint32_t display_w = psx_mod_display_width();
    const int x = 6;
    const int y = display_h > 45u ? (int)display_h - 42 : 160;
    if (!gameplay_active() || display_w == 0u)
        return;
    panel(x, y, 106, 36);
    (void)snprintf(line, sizeof(line), "MONKEYS %02u", caught_monkeys());
    text(line, x + 5, y + 4, color(125u, 235u, 150u));
    (void)snprintf(line, sizeof(line), "TRIANGLES %02u",
                   (unsigned)psx_mod_read_half(TRIANGLES));
    text(line, x + 5, y + 14, color(245u, 214u, 105u));
    (void)snprintf(line, sizeof(line), "SPECTER %02u",
                   (unsigned)psx_mod_read_half(SPECTER_COINS));
    text(line, x + 5, y + 24, color(125u, 200u, 255u));
}

/* This is a progress tracker, not a live spatial minimap. Each pip mirrors
 * one caught/uncaught entry from the game's monkey record table. */
static void enhanced_radar_vblank(void) {
    char line[32];
    const uint32_t width = psx_mod_display_width();
    const unsigned caught = caught_monkeys();
    const int x = width > 132u ? (int)width - 126 : 190;
    const int y = 7;
    unsigned i;
    if (!gameplay_active() || width == 0u)
        return;
    panel(x, y, 120, 45);
    (void)snprintf(line, sizeof(line), "TRACKER %02u/20", caught);
    text(line, x + 5, y + 4, color(180u, 220u, 255u));
    for (i = 0u; i < MONKEY_COUNT; ++i) {
        const int px = x + 6 + (int)(i % 5u) * 22;
        const int py = y + 22 + (int)(i / 5u) * 5;
        const int is_caught =
            psx_mod_read_byte(MONKEY_FLAGS + i * 8u) == 1u;
        rect(px, py, 13, 3,
             is_caught ? color(105u, 230u, 135u) : color(74u, 80u, 94u));
        if (is_caught)
            rect(px + 4, py - 1, 5, 5, color(160u, 255u, 180u));
    }
}

static void speedrun_timer_vblank(void) {
    char line[32];
    const uint32_t width = psx_mod_display_width();
    const unsigned frames = (unsigned)psx_mod_read_half(LEVEL_TIMER);
    const unsigned elapsed = frames / 60u;
    const unsigned minutes = (elapsed / 60u) % 100u;
    const unsigned seconds = elapsed % 60u;
    const unsigned tenths = (frames % 60u) / 6u;
    const int x = width > 104u ? (int)width - 98 : 218;
    if (!gameplay_active() || width == 0u)
        return;
    panel(x, 7, 92, 20);
    (void)snprintf(line, sizeof(line), "RUN %02u:%02u.%u",
                   minutes, seconds, tenths);
    text(line, x + 5, 13, color(255u, 224u, 118u));
}

PSX_MOD_CONSTRUCTOR(register_ape_qol_plugins) {
    (void)psx_mod_register_vblank_plugin("ape.qol.quick-retry", quick_retry_vblank);
    (void)psx_mod_register_activation_plugin("ape.qol.camera-sensitivity",
                                              camera_sensitivity_activate);
    (void)psx_mod_register_vblank_plugin("ape.qol.camera-sensitivity",
                                          camera_sensitivity_vblank);
    (void)psx_mod_register_vblank_plugin("ape.qol.collectible-stats",
                                          collectible_stats_vblank);
    (void)psx_mod_register_vblank_plugin("ape.qol.enhanced-radar",
                                          enhanced_radar_vblank);
    (void)psx_mod_register_vblank_plugin("ape.qol.speedrun-timer",
                                          speedrun_timer_vblank);
}
