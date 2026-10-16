# Original-disc AOT overlays

The USA release precompiles 47 archive overlay images and two minigame
executables. This establishes broad image coverage without requiring a full
decompilation. It does not establish complete static execution coverage.
Interpreter and runtime compilation fallback remain enabled.

Version 0.3.1 fixes two discovery gaps exposed by Primordial Ooze: scheduled
instructions before stack allocation and a return-address save after a long
straight-line prefix. The shared scanner now recovers these original-disc
functions automatically. No runtime captures or per-address seed overrides are
needed to build the release cache.

The consumer profile is [aot/overlays.json](../aot/overlays.json). Extraction,
compilation, auditing, and staging belong to the shared
[psxrecomp AOT pipeline](../psxrecomp-v4/docs/AOT_SHARDING.md), including the
reusable `packed_sector_members` method. There is no Ape-specific extractor.

## Original evidence

Disc: USA SCUS-94423, raw data-track SHA-256
`1ae17e78ebb8c782c7c1785b0a0bd7b0ee28235b8a0c83c8df887129899a852a`.
Discovery used original ISO files and MIPS disassembly of `SCUS_944.23`.
Historical runtime captures and shard caches were not inputs or success criteria.

| Original source | Extent / method |
| --- | --- |
| `KKIIDDZZ.HED` | LBA 355, 2048 bytes; u32 descriptors with high 12 bits = sector count and low 20 bits = logical sector offset. |
| `KKIIDDZZ.DAT` | LBA 356, 58,720,256 bytes; first logical payload. |
| `KKIIDDZZ.BNS` | LBA 29028, 884,736 bytes; second logical payload, physically adjacent to DAT. |
| `MINIGAME/MINI1/MINI1.EXE` | PS-X EXE at 0x80100000, 264,192-byte body. |
| `MINIGAME/MINI2/MINI2.EXE` | PS-X EXE at 0x80100000, 221,184-byte body. |

The BNS payload is exactly covered by 49 descriptors, indices 0x180 through
0x1B0. Forty-seven have established loader destinations:

- Mode table at 0x800AFA30: 8-byte `{entry, member}` records. The loader at
  0x8005BDC0 selects the member and calls 0x800112E4 with destination
  0x80136000, then dispatches through the mode's entry pointer.
- Area records in 0x800A71E0..0x800A8190: 8-byte
  `{member:u16, postprocess:i16, destination:u32}` records, reached through
  the pointer table at 0x800A81B0. The loader at 0x80011104 reads member and
  destination, and 0x800116C0 advances the record chain. Code members have
  postprocess zero and destination 0x8013D000; zero takes the no-op path in
  0x80011970. The area entry is called directly at 0x8005BDA4.
- HED initialization at 0x80011CF8 reads the table and adds HED LBA + 1 to
  each logical offset. Resolver 0x80012C0C masks the low 20 bits for disc
  position and converts the high 12 bits to byte length by shifting 11.
  Loader 0x800112E4 submits the sector count and caller's destination to
  the CD request queue. These established code paths load verbatim bytes;
  no decompression or relocation transform is required.

The profile verifies these loader words, table entries, physical adjacency,
all 49 member classifications, and exact BNS coverage on every extraction.
It supplements automatic discovery for small established members 0x19F,
0x1A3 and 0x1AA. The release AOT inventory contains 49 game-image recipes:
47 archive overlays and two minigame executables. The optional retail
SCPH-1001 BIOS-resident helper is not part of this inventory because the retail
BIOS is not a CI input or included in the release. If a user selects that BIOS,
runtime compilation/interpreter fallback remains available for its resident
helper code.

## Explicit limits

Members 0x185 and 0x1B0 contain plausible code, but no load path was established
in this bounded discovery. Internal references suggest link addresses
0x80146000 and 0x80136000 respectively. They are documented exclusions, not
guessed executable inputs. No claim is made about arbitrary code elsewhere
on disc, every indirect target, or combinations of simultaneously loaded images.

Both release entrypoints freshly extract and compile the same profile for
their platform, then audit ABI/exports, original-byte guards, per-image native
coverage, and the supplied loader entry points. `AOT_CACHE_AUDIT.json` ships
with the resulting inventory and artifact hashes, without game bytes.
Skipping base regeneration or the runtime build does not skip AOT work.

Gameplay spot checks should include the title/attract sequence, a stage entry,
movement and gadgets, an exit and return, and several later stages. Native guard
validation and boot checks do not substitute for the user's gameplay validation.
