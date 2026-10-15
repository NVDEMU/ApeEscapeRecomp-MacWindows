#!/usr/bin/env python3
"""Print a compact MIPS-I listing around known Ape Escape culling sites.

This is a reverse-engineering aid, not a patch generator. It intentionally
reports guest instructions and branch targets without editing the EXE. A draw-
distance patch must still be supported by a traced comparison and an expected-
instruction guard before it is exposed in the mod catalog.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

LOAD_ADDRESS = 0x80010000
TEXT_SIZE = 0x000A5000
PSX_EXE_HEADER = 0x800

REGS = (
    "zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
    "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
    "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
    "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra",
)

# These sites are already guarded/documented by the game's widescreen work.
# Inspect their surrounding code first; they are not assumed to be distance
# culls simply because they are culling-related.
SITES = (
    0x80017228, 0x80017238, 0x80017414, 0x80017424,
    0x80017580, 0x80017590, 0x80017798, 0x800177A8,
    0x800179B4, 0x800179C4, 0x80017BF0, 0x80017C00,
    0x80043D70, 0x80043D94,
    0x80059D28, 0x80059D30, 0x800699F4, 0x800699FC,
    0x8006AE04, 0x8006AE0C, 0x8006D87C, 0x8006D884,
    0x8006DE40, 0x8006DE44, 0x8006F14C, 0x8006F150,
    0x8006F538, 0x8006F540, 0x80084430, 0x80084434,
)


def sign16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def reg(index: int) -> str:
    return "$" + REGS[index]


def decode(pc: int, word: int) -> str:
    op = (word >> 26) & 0x3F
    rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
    shamt, funct, imm = (word >> 6) & 31, word & 63, word & 0xFFFF
    signed = sign16(imm)

    if word == 0:
        return "nop"
    if op == 0:
        names = {
            0x00: f"sll {reg(rd)},{reg(rt)},{shamt}",
            0x02: f"srl {reg(rd)},{reg(rt)},{shamt}",
            0x03: f"sra {reg(rd)},{reg(rt)},{shamt}",
            0x08: f"jr {reg(rs)}",
            0x09: f"jalr {reg(rd)},{reg(rs)}",
            0x21: f"addu {reg(rd)},{reg(rs)},{reg(rt)}",
            0x23: f"subu {reg(rd)},{reg(rs)},{reg(rt)}",
            0x24: f"and {reg(rd)},{reg(rs)},{reg(rt)}",
            0x25: f"or {reg(rd)},{reg(rs)},{reg(rt)}",
            0x26: f"xor {reg(rd)},{reg(rs)},{reg(rt)}",
            0x2A: f"slt {reg(rd)},{reg(rs)},{reg(rt)}",
            0x2B: f"sltu {reg(rd)},{reg(rs)},{reg(rt)}",
            0x0C: "syscall",
        }
        return names.get(funct, f"special/funct=0x{funct:02X} rs={rs} rt={rt} rd={rd}")
    if op in (0x02, 0x03):
        target = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        return f"{'j' if op == 2 else 'jal'} 0x{target:08X}"
    if op in (0x04, 0x05, 0x06, 0x07):
        target = (pc + 4 + (signed << 2)) & 0xFFFFFFFF
        name = {4: "beq", 5: "bne", 6: "blez", 7: "bgtz"}[op]
        if op in (6, 7):
            return f"{name} {reg(rs)},0x{target:08X}"
        return f"{name} {reg(rs)},{reg(rt)},0x{target:08X}"
    if op == 0x0F:
        return f"lui {reg(rt)},0x{imm:04X}"
    immediate = {
        0x08: ("addi", signed), 0x09: ("addiu", signed),
        0x0A: ("slti", signed), 0x0B: ("sltiu", signed),
        0x0C: ("andi", imm), 0x0D: ("ori", imm), 0x0E: ("xori", imm),
        0x20: ("lb", signed), 0x21: ("lh", signed), 0x23: ("lw", signed),
        0x24: ("lbu", signed), 0x25: ("lhu", signed),
        0x28: ("sb", signed), 0x29: ("sh", signed), 0x2B: ("sw", signed),
    }
    if op in immediate:
        name, value = immediate[op]
        if name in ("slti", "sltiu"):
            return f"{name} {reg(rt)},{reg(rs)},{value} (0x{imm:04X})"
        return f"{name} {reg(rt)},{value}({reg(rs)})" if name in (
            "lb", "lh", "lw", "lbu", "lhu", "sb", "sh", "sw"
        ) else f"{name} {reg(rt)},{reg(rs)},{value}"
    if op == 0x12:
        return f"cop2/GTE word=0x{word:08X}"
    return f"op=0x{op:02X} rs={rs} rt={rt} imm=0x{imm:04X}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", type=Path, help="SCUS_944.23 PS-EXE extracted by prepare_disc.py")
    parser.add_argument("--context", type=int, default=8, help="instructions around each known site")
    parser.add_argument("--candidate-context", type=int, default=8, help="instructions around each candidate comparison")
    args = parser.parse_args()
    data = args.exe.read_bytes()
    header = PSX_EXE_HEADER if data[:8] == b"PS-X EXE" else 0
    if len(data) < header + 4:
        raise SystemExit(f"Executable is too small: {len(data)} bytes")
    code_len = min(TEXT_SIZE, len(data) - header)
    instruction_count = code_len // 4

    def word_at(index: int) -> int:
        return struct.unpack_from("<I", data, header + index * 4)[0]

    def pc_at(index: int) -> int:
        return LOAD_ADDRESS + index * 4

    def index_at(address: int) -> int:
        return (address - LOAD_ADDRESS) // 4

    print(f"EXE: {args.exe} ({len(data)} bytes; header={header:#x}; text={code_len:#x})")
    print("Static instruction excerpts only. Candidate comparisons are leads, not verified patches.")
    for site in SITES:
        index = index_at(site)
        if not 0 <= index < instruction_count:
            continue
        start, stop = max(0, index - args.context), min(instruction_count, index + args.context + 1)
        print(f"\n--- around 0x{site:08X} ---")
        for i in range(start, stop):
            word = word_at(i)
            marker = "=>" if i == index else "  "
            print(f"{marker} 0x{pc_at(i):08X}  {word:08X}  {decode(pc_at(i), word)}")

    # High-constant comparisons are only leads: nearby instructions make it
    # easier to distinguish coordinate/texture limits from a possible depth
    # cutoff. The repeated 0x200 family is grouped here because it may describe
    # a shared loop rather than distance.
    candidate_sites = (
        0x800425D8, 0x80044F84, 0x8005A1B4,
        0x8005A648, 0x8005A654, 0x8005A6A8, 0x8005A8B0,
        0x8006ACB0, 0x8006ACC8, 0x8006E7D8,
        0x80083D44, 0x80083D5C, 0x80083D7C, 0x80083D94,
        0x80083DB4, 0x80083DCC, 0x80083E08, 0x80083E20,
        0x80083E40, 0x80083E58, 0x80083E78, 0x80083E90,
    )
    print("\n--- context around high-immediate candidate comparisons (unverified) ---")
    for site in candidate_sites:
        index = index_at(site)
        if not 0 <= index < instruction_count:
            continue
        start, stop = max(0, index - args.candidate_context), min(
            instruction_count, index + args.candidate_context + 1
        )
        print(f"\n--- candidate around 0x{site:08X} ---")
        for i in range(start, stop):
            word = word_at(i)
            marker = "=>" if i == index else "  "
            print(f"{marker} 0x{pc_at(i):08X}  {word:08X}  {decode(pc_at(i), word)}")

    print("\n--- immediate comparisons near render/cull code ---")
    ranges = (
        (0x80016000, 0x80019000), (0x80042000, 0x80045000),
        (0x80059000, 0x8005C000), (0x80068000, 0x80071000),
        (0x80083000, 0x80085000),
    )
    count = 0
    for i in range(instruction_count):
        pc = pc_at(i)
        if not any(low <= pc < high for low, high in ranges):
            continue
        word = word_at(i)
        op, imm = (word >> 26) & 0x3F, word & 0xFFFF
        if op not in (0x0A, 0x0B):
            continue
        value = sign16(imm) if op == 0x0A else imm
        if value < 64:
            continue
        print(f"0x{pc:08X}  {word:08X}  {decode(pc, word)}")
        count += 1
    if count == 0:
        print("(no SLTI/SLTIU immediates >= 64 in selected code ranges)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
