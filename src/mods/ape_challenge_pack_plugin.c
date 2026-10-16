#include "mod_plugins.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

/* Ape Escape Challenge Pack. Every entry is an explicit, default-off feature. */
static const uint32_t PHASE=0x800F447Cu, TIMER=0x800F4490u, LIVES=0x800F448Cu;
static const uint32_t HEALTH=0x800EC2C8u, COINS=0x800F44BAu;
static const uint32_t MONKEY_FLAGS=0x80139368u, GP0=0x1F801810u;
enum { PHASE_PLAYING=3u, TIMER_RATE=60u, RULE_TIME=0u,
       RULE_NO_DAMAGE=1u, RULE_LIVES=2u, RULE_UNSELECTED=0xFFu };
typedef struct Glyph { char ch; uint8_t rows[7]; } Glyph;

/* 5x7 glyphs for the compact in-game challenge HUD. */
static const Glyph FONT[] = {
 {'A',{14,17,17,31,17,17,17}}, {'D',{30,17,17,17,17,17,30}},
 {'E',{31,16,16,30,16,16,31}}, {'F',{31,16,16,30,16,16,16}},
 {'G',{14,17,16,23,17,17,15}}, {'H',{17,17,17,31,17,17,17}},
 {'I',{14,4,4,4,4,4,14}}, {'L',{16,16,16,16,16,16,31}},
 {'M',{17,27,21,21,17,17,17}}, {'N',{17,25,25,21,19,19,17}},
 {'O',{14,17,17,17,17,17,14}}, {'P',{30,17,17,30,16,16,16}},
 {'R',{30,17,17,30,20,18,17}}, {'S',{15,16,16,14,1,1,30}},
 {'T',{31,4,4,4,4,4,4}}, {'U',{17,17,17,17,17,17,14}},
 {'V',{17,17,17,17,17,10,4}},
 {'0',{14,17,19,21,25,17,14}}, {'1',{4,12,4,4,4,4,14}},
 {'2',{14,17,1,2,4,8,31}}, {'3',{30,1,1,14,1,1,30}},
 {'4',{2,6,10,18,31,2,2}}, {'5',{31,16,16,30,1,1,30}},
 {'6',{14,16,16,30,17,17,14}}, {'7',{31,1,2,4,8,8,8}},
 {'8',{14,17,17,14,17,17,14}}, {'9',{14,17,19,15,1,1,14}},
 {':',{0,4,4,0,4,4,0}}
};
static uint32_t rgb(uint8_t r,uint8_t g,uint8_t b) {
 return (uint32_t)r|((uint32_t)g<<8u)|((uint32_t)b<<16u);
}
static void rectangle(int x,int y,int w,int h,uint32_t color) {
 if(w<=0||h<=0||x < -512||y < -512||x>2048||y>2048) return;
 psx_mod_write_word(GP0,0x60000000u|color);
 psx_mod_write_word(GP0,((uint32_t)(uint16_t)y<<16u)|(uint32_t)(uint16_t)x);
 psx_mod_write_word(GP0,((uint32_t)(uint16_t)h<<16u)|(uint32_t)(uint16_t)w);
}
static uint8_t glyph_row(char ch,unsigned row) {
 size_t i; if(row>=7u) return 0u;
 for(i=0;i<sizeof(FONT)/sizeof(FONT[0]);++i)
  if(FONT[i].ch==ch) return FONT[i].rows[row];
 return 0u;
}
static void draw_text(const char *s,int x,int y,uint32_t color) {
 if(!s) return;
 for(;*s;++s,x+=6) for(unsigned row=0;row<7u;++row) {
  const uint8_t bits=glyph_row(*s,row); int col=0;
  while(col<5) {
   int start;
   if(!(bits&(uint8_t)(1u<<(4-col)))) { ++col; continue; }
   start=col;
   while(col<5&&(bits&(uint8_t)(1u<<(4-col)))) ++col;
   rectangle(x+start,y+(int)row,col-start,1,color);
  }
 }
}
static void draw_hud(const char *title,const char *status) {
 const uint32_t w=psx_mod_display_width(),h=psx_mod_display_height();
 const int x=7,y=7; const uint32_t edge=rgb(87u,105u,129u);
 if(w<122u||h<40u) return;
 rectangle(x,y,114,29,rgb(15u,19u,27u));
 rectangle(x,y,114,1,edge); rectangle(x,y+28,114,1,edge);
 rectangle(x,y,1,29,edge); rectangle(x+113,y,1,29,edge);
 draw_text(title,x+5,y+3,rgb(180u,220u,255u));
 draw_text(status,x+5,y+16,rgb(255u,224u,118u));
}
static int playing(void) {
 return psx_mod_game_started()&&psx_mod_read_byte(PHASE)==PHASE_PLAYING;
}
static unsigned option_number(const char *feature,const char *option,unsigned fallback) {
 char value[16]={0}; unsigned parsed;
 if(!psx_mod_option_value("ape.enhancement.challenge-pack",feature,option,value,(uint32_t)sizeof(value)))
  return fallback;
 parsed=(unsigned)strtoul(value,NULL,10); return parsed;
}
static unsigned time_limit(const char *feature) {
 unsigned n=option_number(feature,"time-limit",300u);
 return n==180u||n==300u||n==600u?n:300u;
}
static unsigned starting_lives(const char *feature) {
 unsigned n=option_number(feature,"starting-lives",3u);
 return n==1u||n==3u||n==5u?n:3u;
}

/* Use the game's own 60 Hz stage timer; timeout follows normal death handling. */
static void run_time_trial(unsigned limit,const char *title,int *timed_out) {
 char status[24]; unsigned frames,left,minutes,seconds;
 if(!playing()) { *timed_out=0; return; }
 frames=(unsigned)psx_mod_read_half(TIMER);
 if(frames>=limit*TIMER_RATE) {
  if(!*timed_out) psx_mod_counter_add("ape.challenge.time-trial.timeout",1u);
  *timed_out=1; psx_mod_write_half(HEALTH,0u); draw_hud(title,"TIME UP"); return;
 }
 *timed_out=0; left=limit*TIMER_RATE-frames;
 minutes=(left/TIMER_RATE)/60u; seconds=(left/TIMER_RATE)%60u;
 (void)snprintf(status,sizeof(status),"TIME %02u:%02u",minutes,seconds);
 draw_hud(title,status);
}

/* Any observed health drop fails; keep HP at zero until normal death transition. */
static void run_no_damage(int *valid,int *failed,uint16_t *previous,const char *title) {
 uint16_t health;
 if(!playing()) { *valid=0; *failed=0; return; }
 health=psx_mod_read_half(HEALTH);
 if(!*valid) { *previous=health; *valid=1; }
 else if(!*failed&&health<*previous) {
  *failed=1; psx_mod_counter_add("ape.challenge.no-damage.failed",1u);
 }
 if(*failed) { psx_mod_write_half(HEALTH,0u); draw_hud(title,"RUN FAILED"); }
 else { *previous=health; draw_hud(title,"NO DAMAGE"); }
}

/* Set lives only on the first active-play frame; don't refill every stage. */
static void run_limited_lives(unsigned count,int *applied,const char *title) {
 char status[24];
 if(!playing()) return;
 if(!*applied) {
  psx_mod_write_half(LIVES,(uint16_t)count); *applied=1;
  psx_mod_counter_add("ape.challenge.limited-lives.started",1u);
 }
 (void)snprintf(status,sizeof(status),"LIVES %02u",(unsigned)psx_mod_read_half(LIVES));
 draw_hud(title,status);
}

static unsigned g_time_limit=300u; static int g_timed_out;
static void activate_time_trial(void) { g_time_limit=time_limit("time-trial"); g_timed_out=0; }
static void time_trial_vblank(void) { run_time_trial(g_time_limit,"TIME TRIAL",&g_timed_out); }

static int g_damage_valid,g_damage_failed; static uint16_t g_previous_health;
static void activate_no_damage(void) { g_damage_valid=0; g_damage_failed=0; g_previous_health=0u; }
static void no_damage_vblank(void) {
 run_no_damage(&g_damage_valid,&g_damage_failed,&g_previous_health,"NO DAMAGE RUN");
}
static unsigned g_life_limit=3u; static int g_lives_applied;
static void activate_limited_lives(void) { g_life_limit=starting_lives("limited-lives"); g_lives_applied=0; }
static void limited_lives_vblank(void) { run_limited_lives(g_life_limit,&g_lives_applied,"LIMITED LIVES"); }

/* Pick one rule on the first playable frame, then keep it for the app session.
 * Mix clock and current stage values without touching the game's own RNG. */
static unsigned g_random_time=300u,g_random_lives=3u;
static uint8_t g_random_rule=RULE_UNSELECTED;
static int g_random_timed_out,g_random_damage_valid,g_random_damage_failed,g_random_lives_applied;
static uint16_t g_random_previous_health;
static void activate_random_challenge(void) {
 g_random_time=time_limit("random-challenge"); g_random_lives=starting_lives("random-challenge");
 g_random_rule=RULE_UNSELECTED; g_random_timed_out=0; g_random_damage_valid=0;
 g_random_damage_failed=0; g_random_previous_health=0u; g_random_lives_applied=0;
}
static uint32_t random_seed(void) {
 uint32_t seed=(uint32_t)time(NULL);
 seed^=(uint32_t)psx_mod_read_half(TIMER)*0x9E3779B9u;
 seed^=(uint32_t)psx_mod_read_half(LIVES)<<16u;
 seed^=(uint32_t)psx_mod_read_half(COINS)*0x85EBCA6Bu;
 seed^=(uint32_t)psx_mod_read_byte(MONKEY_FLAGS)<<24u;
 if(!seed) seed=0xA341316Cu;
 seed^=seed<<13u; seed^=seed>>17u; seed^=seed<<5u; return seed;
}
static void random_challenge_vblank(void) {
 if(!playing()) { g_random_damage_valid=0; g_random_damage_failed=0; return; }
 if(g_random_rule==RULE_UNSELECTED) {
  g_random_rule=(uint8_t)(random_seed()%3u);
  if(g_random_rule==RULE_TIME) psx_mod_counter_add("ape.challenge.random.selected-time-trial",1u);
  else if(g_random_rule==RULE_NO_DAMAGE) psx_mod_counter_add("ape.challenge.random.selected-no-damage",1u);
  else psx_mod_counter_add("ape.challenge.random.selected-limited-lives",1u);
 }
 if(g_random_rule==RULE_TIME) run_time_trial(g_random_time,"RANDOM: TIME",&g_random_timed_out);
 else if(g_random_rule==RULE_NO_DAMAGE)
  run_no_damage(&g_random_damage_valid,&g_random_damage_failed,&g_random_previous_health,"RANDOM: NO HIT");
 else if(g_random_rule==RULE_LIVES)
  run_limited_lives(g_random_lives,&g_random_lives_applied,"RANDOM: LIVES");
}
PSX_MOD_CONSTRUCTOR(register_ape_challenge_pack) {
 (void)psx_mod_register_activation_plugin("ape.challenge.time-trial",activate_time_trial);
 (void)psx_mod_register_vblank_plugin("ape.challenge.time-trial",time_trial_vblank);
 (void)psx_mod_register_activation_plugin("ape.challenge.no-damage",activate_no_damage);
 (void)psx_mod_register_vblank_plugin("ape.challenge.no-damage",no_damage_vblank);
 (void)psx_mod_register_activation_plugin("ape.challenge.limited-lives",activate_limited_lives);
 (void)psx_mod_register_vblank_plugin("ape.challenge.limited-lives",limited_lives_vblank);
 (void)psx_mod_register_activation_plugin("ape.challenge.random-challenge",activate_random_challenge);
 (void)psx_mod_register_vblank_plugin("ape.challenge.random-challenge",random_challenge_vblank);
}
