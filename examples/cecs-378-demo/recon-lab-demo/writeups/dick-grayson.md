---
real-name: Dick Grayson
csulb-id: "040100102"
handle: "Nightbyte"
seed-fingerprint: "778899"
flag1: CECS378{vuln1_4c8ba190}
flag2: CECS378{vuln2_71fe23dd}
honor-flag: CECS378{honor_a90e6b14}
---

# After-Action Report -- Buffer Overflow Lab

[--[ 0.0 -- TARGET ]--]

- **Env:** GitHub Codespace, `ubuntu-22.04`, gcc 11.4.0, gdb 12.1, glibc 2.35. Compiled with the provided `Makefile` (`-m32 -fno-stack-protector -z execstack -no-pie`; vuln2 without `execstack`).
- **Started:** 2026-06-24. **Finished:** 2026-06-27. Roughly 9 hours; Ω was where I lost most of the time.
- **Seed line:** `seed=778899 :: derive(dick-grayson) -> {vuln1: stack_smash_std, vuln2: nx_ret2libc}`. Seed fingerprint `778899` pins my two binaries and flags.

Handle's Nightbyte because most of this got done after midnight. Mechanism writeup below.

[--[ 1.0 -- RECON ]--]

**vuln1 (`./vuln1`) -- classic stack smash.**

The vulnerable call is `strcpy(buffer, argv[1])` into `char buffer[64]`. I broke on the function, sent an overlong argument, and pulled the frame:

```
(gdb) break vuln_func
(gdb) run $(python3 -c 'print("A"*100)')
(gdb) info frame
Stack level 0, frame at 0xffffd380:
 eip = 0x080491e8 in vuln_func (vuln1.c:14); saved eip = 0x41414141
 called by frame at 0xffffd3a0
 Saved registers:
  ebp at 0xffffd378, eip at 0xffffd37c
```

Saved EIP already sitting at `0x41414141`, so the overflow reaches it. Stack dump to locate the buffer:

```
(gdb) x/40wx $esp
0xffffd330: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd340: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd350: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd360: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd370: 0x41414141 0x41414141 0x41414141 0x41414141
0xffffd380: 0xffffd460 0x00000002 0x08049250 0xf7fb0000
0xffffd390: 0x00000000 0xf7c23eab 0xf7fb0000 0x00000000
0xffffd3a0: 0x00000000 0xf7c23eab 0x00000002 0xffffd434
0xffffd3b0: 0xffffd440 0xffffd3d0 0x00000000 0x00000000
0xffffd3c0: 0x00000000 0xf7ffcb80 0xf7ffd000 0x00000000
```

`buffer` starts at `0xffffd330`. Saved EIP is at `0xffffd37c` (from `info frame`). So:

**offset = 0xffffd37c - 0xffffd330 = 0x4c = 76 bytes** (64 buffer + 8 padding + 4 saved EBP before the return address). I double-checked with a `AAAABBBB...` marker string and the word that landed in EIP matched byte position 76. Confirmed 76.

For **vuln2** I did *not* redo the full `info frame` / `x/40wx` recon separately -- I assumed the same 76-byte layout since the source looked identical (`char buffer[64]`, same `strcpy` sink) and my Ω payload used offset 76 and worked. So I'm confident the number is right, but I'm noting I inferred it from vuln1 rather than proving it independently on vuln2. The one thing I *did* check on vuln2 was `readelf -l vuln2 | grep GNU_STACK`, which shows `RW` (no execute bit) -- that's the NX difference that forces Phase Ω.

[--[ 2.0 -- PHASE PHI ACE ]--]

Phase Φ is the shellcode-on-stack exploit against `vuln1`. `exploit1.c` builds `[NOP sled][shellcode][return address]`.

**Shellcode byte choice.** I used the standard 25-byte null-free `execve("/bin/sh")` stub. The reason null-free matters: the sink is `strcpy`, and `strcpy` stops copying at the first `0x00` byte. If my shellcode contained a null, the payload would be truncated right there and never reach EIP. That's why the stub zeroes registers with `xor eax, eax` instead of `mov eax, 0` -- the `mov` immediate assembles with `0x00` bytes, the `xor` doesn't. I disassembled the stub with `objdump -d` and searched for `00` to be sure.

**NOP sled sizing.** 76 bytes to reach EIP, shellcode is 25, so I put `76 - 25 = 51` bytes of `0x90` in front, then the shellcode, then the 4-byte return address. I aimed the return into the middle of the sled rather than at the exact shellcode start, so small differences in the stack address between gdb and a normal run wouldn't cause a miss -- landing anywhere in the 51-byte sled slides down into the shellcode.

**Offset source.** The `76` derived in §1.0; `exploit1.c` has `#define OFFSET 76`.

**Reading the leaked &buffer.** The harness prints `buffer @ 0xffffd330` at startup. My exploit reads that with `sscanf` and computes the return target as `buf_addr + 30` -- 30 bytes into the sled, comfortably before the shellcode at byte 51. So EIP = `0xffffd330 + 30 = 0xffffd34e`, a NOP, riding down into `execve`. In code: `memset(buf,0x90,OFFSET-SC); memcpy(buf+OFFSET-SC,shell,SC); *(unsigned*)(buf+OFFSET)=leak+30;`.

Popped a shell after a couple of tries (first attempt I aimed too close to the shellcode start and it still worked, +30 was more reliable). `id` confirmed.

![phi shell](screenshots/phase-phi-shell.png)
![gdb landing in sled](screenshots/phase-phi-gdb.png)

Flag: `CECS378{vuln1_4c8ba190}`.

[--[ 3.0 -- PHASE OMEGA ACE ]--]

Phase Ω is `vuln2` with a non-executable stack. Return-to-libc.

**(3a) Why Φ fails here.** Running my Φ payload against `vuln2` segfaults immediately:

```
Program received signal SIGSEGV, Segmentation fault.
0xffffd358 in ?? ()
```

EIP successfully jumps to my sled address, but the processor refuses to execute it: the `GNU_STACK` segment is `RW` (NX bit set), so the stack is a data-only region. My injected shellcode is just bytes that will never run as code. The way around it is to not inject any code at all -- instead point the return address at a function that's *already* in an executable page, i.e. libc. That's return-to-libc.

**(3b) libc offset hunting.** The plan is to call `system("/bin/sh")` out of libc. I need the address of `system` and the address of the `"/bin/sh"` string. Runtime lookup first:

```
(gdb) info proc mappings
 0xf7c00000 0xf7c22000 r--p  libc.so.6
(gdb) p system
$1 = {<text>} 0xf7c4a230 <system>
```

Then static offsets so the exploit doesn't depend on a gdb session:

```
$ readelf -s /lib/i386-linux-gnu/libc.so.6 | grep ' system@'
   1500: 0004a230   55 FUNC GLOBAL DEFAULT system@@GLIBC_2.0
$ nm -D /lib/i386-linux-gnu/libc.so.6 | grep '\bexit\b'
0003d4a0 T exit
$ strings -a -t x /lib/i386-linux-gnu/libc.so.6 | grep '/bin/sh'
 1c3d88 /bin/sh
```

Offsets: `system=0x0004a230`, `exit=0x0003d4a0`, `"/bin/sh"=0x001c3d88`. With libc base `0xf7c00000`, the absolute addresses are `system=0xf7c4a230`, `exit=0xf7c3d4a0`, `binsh=0xf7dc3d88`. My payload after the 76-byte filler is `[&system][&exit][&"/bin/sh"]` -- `exit` is the fake return address so the program exits cleanly after the shell instead of segfaulting on teardown.

**(3c) setuid / setreuid privilege fix.** `vuln2` is setuid-root, but the shell `system` spawns drops back to my real uid, because bash lowers its privileges when the effective uid doesn't match the real uid. The fix is to call `setreuid(0,0)` in the chain before `system`, so both real and effective uid are root and the shell won't demote itself. From `man 2 setreuid`: *"setreuid() sets real and effective user IDs of the calling process. ... If the real user ID is set or the effective user ID is set to a value not equal to the previous real user ID, the saved set-user-ID will be set to the new effective user ID."* I passed real=0 and effective=0. After adding the call, `id` inside the popped shell reported `euid=0(root)` and I got the flag.

Address `setreuid = 0xf7c00000 + 0x000d5a10 = 0xf7cd5a10` (from `nm -D`).

![omega ret2libc in gdb](screenshots/phase-omega-chain.png)
![omega root shell](screenshots/phase-omega-root.png)

Flag: `CECS378{vuln2_71fe23dd}`.

[--[ 4.0 -- AFTERMATH ]--]

**Which phase was harder, and why.** Ω, clearly. Φ is close to deterministic once you have the offset -- it's arithmetic plus a sled that forgives small addressing mistakes. Ω needed several exact libc addresses at once, and every one is a place where a single wrong word means a silent segfault that doesn't tell you which part broke. I spent a long time changing one address, rerunning, getting the identical crash, and having to reason about which stack word was wrong. Chaining `setreuid` in front of `system` was the fiddliest part and where I burned the most time. Φ never put me in that loop.

**No-leak counterfactual.** If the harness hadn't leaked `&buffer`, Φ would have to defeat stack ASLR. My best options would be to blow up the NOP sled as large as possible and brute-force across many runs, hoping one randomized stack layout drops EIP somewhere in the sled -- or to find a separate info leak (like a format-string bug) that hands me a live stack pointer. For Ω under library ASLR it's worse: I'd first need to leak a libc address (for example ROP into `puts` on a GOT entry to print a real function address), compute the libc base from the known offset, and only then run the ret2libc as a second stage. The provided leak is what makes this a lab instead of a research project.

**Canary -> `__stack_chk_fail`.** If the binary were built with `-fstack-protector`, the compiler inserts a random canary value between `buffer` and the saved EBP/EIP. My 76-byte `strcpy` overwrite would clobber the canary on the way to the return address. In the function's epilogue, generated code compares the canary on the stack against the master copy stored in thread-local storage; if they differ it calls `__stack_chk_fail`, which prints `*** stack smashing detected ***` and calls `abort()` -- all *before* the return instruction loads the overwritten EIP. So my overflow would be detected and killed at return time. Getting around it requires either leaking the canary value first and writing the exact same bytes back into the payload, or a write primitive that skips over the canary word entirely.

**Cited source.** Aleph One, "Smashing the Stack for Fun and Profit," *Phrack* 49:14 (1996). The `[NOP sled | shellcode | return address]` payload layout and the idea of pointing EIP into the sled instead of at an exact address both come from that paper. It was pretty cool that a paper this old lined up almost exactly with a modern Codespace target.

Honor flag: `CECS378{honor_a90e6b14}` -- this is my own work; all gdb output and screenshots are from my own Codespace; I didn't share or borrow payloads.
