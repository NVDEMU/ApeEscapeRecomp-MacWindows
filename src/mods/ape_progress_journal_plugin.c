#include "mod_plugins.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <direct.h>
#else
#include <sys/stat.h>
#endif

/* Local-only observer: no guest RAM writes; append only after active gameplay stops.
 * Era/level addresses originate in community notes and still need validation for US SCUS-94423. */
static const uint32_t PHASE=0x800F447Cu, TIMER=0x800F4490u, LIVES=0x800F448Cu;
static const uint32_t TRIANGLES=0x800F44B8u, COINS=0x800F44BAu, MONKEY_FLAGS=0x80139368u;
static const uint32_t CURRENT_ERA=0x80139AF8u, CURRENT_LEVEL=0x80139B00u;
enum { PHASE_PLAYING=3u, MONKEY_RECORDS=20u };
#define INVALID_STAGE 0xFFFFFFFFu
typedef struct ApeProgressSnapshot {
    uint32_t stage_id,frames,caught,triangles,coins,lives,mask;
    int valid;
} ApeProgressSnapshot;
static ApeProgressSnapshot g_snapshot;
static int g_in_play;

static int data_dir(char* out,size_t cap) {
    const char* override_dir=getenv("APE_ESCAPE_RECOMP_DATA_DIR");
    if(override_dir && override_dir[0]) {
        if(snprintf(out,cap,"%s",override_dir)>=(int)cap)return 0;
        return 1;
    }
#ifdef _WIN32
    const char* base=getenv("APPDATA"); char parent[768];
    if(!base || !base[0])return 0;
    if(snprintf(parent,sizeof(parent),"%s\\NVDEMU",base)>=(int)sizeof(parent))return 0;
    (void)_mkdir(parent);
    if(snprintf(out,cap,"%s\\Ape Escape Recompiled - Enhanced Edition",parent)>=(int)cap)return 0;
    (void)_mkdir(out); return 1;
#elif defined(__APPLE__)
    const char* home=getenv("HOME"); char parent[768];
    if(!home || !home[0])return 0;
    if(snprintf(parent,sizeof(parent),"%s/Library/Application Support",home)>=(int)sizeof(parent))return 0;
    (void)mkdir(parent,0700);
    if(snprintf(out,cap,"%s/Ape Escape Recompiled",parent)>=(int)cap)return 0;
    (void)mkdir(out,0700); return 1;
#else
    const char* base=getenv("XDG_DATA_HOME"); char parent[768];
    if(base && base[0]) {
        if(snprintf(parent,sizeof(parent),"%s/NVDEMU",base)>=(int)sizeof(parent))return 0;
        (void)mkdir(base,0700); (void)mkdir(parent,0700);
    } else {
        const char* home=getenv("HOME");
        if(!home || !home[0])return 0;
        if(snprintf(parent,sizeof(parent),"%s/.local/share/NVDEMU",home)>=(int)sizeof(parent))return 0;
        (void)mkdir(parent,0700);
    }
    if(snprintf(out,cap,"%s/Ape Escape Recompiled - Enhanced Edition",parent)>=(int)cap)return 0;
    (void)mkdir(out,0700); return 1;
#endif
}
static uint32_t stage_id(void) {
    const uint32_t era=psx_mod_read_byte(CURRENT_ERA), level=psx_mod_read_byte(CURRENT_LEVEL);
    if(era<=5u && level<=2u)return era*10u+level;
    if(era==6u && level==0u)return 60u;
    if(era==7u && level==0u)return 70u;
    if(era==8u && level==0u)return 80u;
    if(era==9u && level==0u)return 90u;
    return INVALID_STAGE;
}
static void sample_game_state(void) {
    unsigned i;
    g_snapshot.stage_id=stage_id();
    g_snapshot.frames=psx_mod_read_half(TIMER);
    g_snapshot.triangles=psx_mod_read_half(TRIANGLES);
    g_snapshot.coins=psx_mod_read_half(COINS);
    g_snapshot.lives=psx_mod_read_half(LIVES);
    g_snapshot.caught=0u; g_snapshot.mask=0u;
    g_snapshot.valid=g_snapshot.stage_id!=INVALID_STAGE;
    for(i=0u;i<MONKEY_RECORDS;++i) {
        if(psx_mod_read_byte(MONKEY_FLAGS+i*8u)==1u) {
            ++g_snapshot.caught; g_snapshot.mask|=(uint32_t)1u<<i;
        }
    }
}
static void append_snapshot(void) {
    char dir[1024], path[1200]; FILE* out;
    if(!g_snapshot.valid || !data_dir(dir,sizeof(dir)))return;
#ifdef _WIN32
    if(snprintf(path,sizeof(path),"%s\\ape_escape_journal.tsv",dir)>=(int)sizeof(path))return;
#else
    if(snprintf(path,sizeof(path),"%s/ape_escape_journal.tsv",dir)>=(int)sizeof(path))return;
#endif
    out=fopen(path,"a"); if(!out)return;
    (void)fprintf(out,"%u\t%lld\t%u\t%u\t%u\t%u\t%u\t%08X\n",
        g_snapshot.stage_id,(long long)time(NULL),g_snapshot.frames,g_snapshot.caught,
        g_snapshot.triangles,g_snapshot.coins,g_snapshot.lives,g_snapshot.mask);
    (void)fclose(out);
    psx_mod_counter_add("ape.progress-journal.records",1u);
}
static void reset_journal(void) {
    memset(&g_snapshot,0,sizeof(g_snapshot)); g_snapshot.stage_id=INVALID_STAGE; g_in_play=0;
}
static void journal_vblank(void) {
    const int playing=psx_mod_game_started() && psx_mod_read_byte(PHASE)==PHASE_PLAYING;
    if(playing) { sample_game_state(); g_in_play=1; return; }
    if(g_in_play) append_snapshot();
    g_in_play=0;
}
PSX_MOD_CONSTRUCTOR(register_ape_progress_journal) {
    (void)psx_mod_register_activation_plugin("ape.progress-journal.capture",reset_journal);
    (void)psx_mod_register_vblank_plugin("ape.progress-journal.capture",journal_vblank);
}
