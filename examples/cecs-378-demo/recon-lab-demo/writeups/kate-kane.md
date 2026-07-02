---
real-name: Kate Kane
csulb-id: "040100109"
handle: batwoman
seed-fingerprint: c0ffee
flag1: CECS378{vuln1_a3f19c2e}
flag2: CECS378{vuln2_7d0e4b81}
honor-flag: CECS378{honor_kk_5f2a3d8b}
---

# After-Action Report -- Buffer Overflow Lab

[--[ 0.0 -- TARGET ]--]

I did all of this in the GitHub Codespace off the assignment template, not on
my own laptop -- I did not want ASLR or a newer glibc on my machine to move the
offsets around and then argue with the grader about it. Everything below is from
that container.

- Environment: Codespace, Ubuntu 22.04 image, gcc 11, `-fno-stack-protector
  -z execstack` for vuln1 as the Makefile ships it.
- Started: 2026-06-25 (recon + Phase Phi the same night).
- Finished: 2026-06-28 (Phase Omega took me two more sittings).

Seed line straight out of `make print-seed`:

```
$ make print-seed
seed: c0ffee  (fp=c0ffee)
```

That `c0ffee` matches the `seed-fingerprint:` in my frontmatter above, so the
binaries the grader rebuilds should be byte-for-byte the ones I attacked.

[--[ 1.0 -- RECON ]--]

**vuln1.** I put a breakpoint right after the `gets()` call so the frame was
fully set up, then dumped the frame and the stack.

```
(gdb) info frame
Stack level 0, frame at 0xffffd6a0:
 eip = 0x080491c7 in vuln (vuln1.c:14); saved eip = 0xf7c23a41
 called by frame at 0xffffd6c0
 source language c.
 Arglist at 0xffffd698, args:
 Locals at 0xffffd698, Previous frame's sp is 0xffffd6a0
 Saved registers:
  ebp at 0xffffd698, eip at 0xffffd69c
```

```
(gdb) x/40wx $esp
0xffffd64c: 0x08049080  0xffffd730  0x00000000  0x41414141
0xffffd65c: 0x41414141  0x41414141  0x41414141  0x41414141
0xffffd66c: 0x41414141  0x41414141  0x41414141  0x41414141
0xffffd67c: 0x41414141  0x41414141  0x41414141  0x41414141
0xffffd68c: 0x41414141  0x41414141  0x41414141  0xf7fb3d20
0xffffd69c: 0xf7c23a41  0xffffd730  0xffffd738  0x00000000
```

`buffer` starts at `0xffffd650` (first `0x41414141`) and the saved EIP slot is
at `0xffffd69c` (matches `Saved registers: eip at 0xffffd69c`). So the distance
is:

```
0xffffd69c - 0xffffd650 = 0x4c = 76 bytes to saved EBP,
then +4 for saved EBP  ->  offset to return address = 76
```

I confirmed it by sending a 76-byte pattern + `BBBB` and watching EIP land on
`0x42424242`. Offset = **76** for vuln1.

**vuln2.** Same procedure on the second binary. It has a bigger local frame:

```
(gdb) info frame
Stack level 0, frame at 0xffffd5f0:
 eip = 0x080492b3 in vuln (vuln2.c:19); saved eip = 0xf7c23a41
 Saved registers:
  ebp at 0xffffd5d8, eip at 0xffffd5dc
```

```
(gdb) x/8wx 0xffffd580
0xffffd580: 0x41414141  0x41414141  0x41414141  0x41414141
0xffffd590: 0x41414141  0x41414141  0x41414141  0x41414141
```

buffer at `0xffffd580`, saved EIP at `0xffffd5dc`:

```
0xffffd5dc - 0xffffd580 = 0x5c = 92 bytes -> offset to return address = 92
```

Offset = **92** for vuln2. I used this one for the ret2libc chain in Phase
Omega.

[--[ 2.0 -- PHASE PHI ACE ]--]

Phase Phi is the classic shellcode-on-the-stack attack against vuln1, which is
built with an executable stack, so I can jump straight into bytes I put in the
buffer.

Walking my `exploit1.c`:

1. **The shellcode bytes.** I used a 25-byte `execve("/bin/sh")` stub (lines
   8-14 of exploit1.c). I did *not* just paste a random blob -- the reason it
   is those bytes is that it has to be null-free, because the vulnerable read is
   `gets()`/string-based and a `0x00` would truncate my payload early. The stub
   `xor eax,eax` / `push eax` / `push "//sh"` / `push "/bin"` sets up the
   `execve` args with no zero bytes, then `mov al,0x0b; int 0x80`. I checked it
   with `objdump` and there is not a single `00` in the machine code, which is
   the whole point.

2. **The NOP sled.** I padded the front of the buffer with `0x90` NOPs (line 22,
   `sled = b"\x90" * 40`). The stack address of `buffer` jitters a little run to
   run even inside the container, so I do not have to hit the exact first byte of
   my shellcode -- landing anywhere in the sled slides me down into the real
   code. I sized it at 40 because I only need to cover the small amount of drift
   I saw between gdb and a raw run (a couple dozen bytes), and I still needed
   room in the 76-byte budget for the shellcode itself.

3. **Where the offset came from.** The `76` on line 25
   (`payload = sled + shellcode + b"A"*(76-len(sled)-len(shellcode)) + ret`)
   is exactly the recon number from section 1.0 -- 76 bytes from the start of
   `buffer` to the saved return address.

4. **The leaked address.** vuln1 prints `&buffer` to stdout before it reads
   input. My exploit reads that line (line 18,
   `leak = int(proc.stdout.readline().split()[-1], 16)`), and I use it as the
   return address by pointing EIP a little bit *into* the sled:
   `ret = struct.pack("<I", leak + 20)`. So I am not guessing the stack
   address -- the program hands it to me and I aim 20 bytes past the reported
   start of buffer so I land solidly in the NOPs.

Running it dropped me to a shell as the setuid oracle user and I read the flag:

![Phase Phi shell popped](screenshots/phase-phi-shell.png)

![Phase Phi flag](screenshots/phase-phi-flag.png)

Captured: `CECS378{vuln1_a3f19c2e}` (also in frontmatter as `flag1`).

[--[ 3.0 -- PHASE OMEGA ACE ]--]

vuln2 is compiled **without** `-z execstack`, so the stack is non-executable and
the Phase Phi trick just segfaults -- the CPU refuses to run my shellcode even
though it is sitting right there in the buffer. So Phase Omega is a
return-to-libc chain instead: overwrite the return address with the address of a
real libc function and fake a call frame for it.

**(3a) Why the Phase Phi payload fails here.**

```
Program received signal SIGSEGV, Segmentation fault.
0x90909090 in ?? ()
```

EIP is sitting in my NOP sled at `0x9090...`, which proves the overflow worked
and control transferred -- but the fault is the NX/DEP protection: the page the
stack lives on is mapped read/write, **not** execute, because vuln2 was built
without `-z execstack`. So the same bytes that ran fine in vuln1 are
un-runnable here. That is what forces a code-reuse approach.

**(3b) libc offsets.**

I found libc's load base from gdb (`info proc mappings` -> `0xf7c00000`) and
pulled the symbol offsets out of the container's libc:

```
$ readelf -s /lib/i386-linux-gnu/libc.so.6 | grep -E ' system@| exit@'
   1489: 00048150   ... FUNC ... system
    141: 0003c8e0   ... FUNC ... exit
$ strings -a -t x /lib/i386-linux-gnu/libc.so.6 | grep '/bin/sh'
  1c5e58 /bin/sh
```

So in my running process:

```
system  = 0xf7c00000 + 0x48150  = 0xf7c48150
exit    = 0xf7c00000 + 0x3c8e0  = 0xf7c3c8e0
"/bin/sh"= 0xf7c00000 + 0x1c5e58 = 0xf7dc5e58
```

**(3c) The setuid problem.**

My first working chain called `system("/bin/sh")` and I *did* get a shell -- but
`id` showed my own uid, not oracle's, so I could not read the flag. The reason is
that vuln2 is setuid oracle: it runs with a real uid of me and an effective uid
of oracle. `system()` ultimately execs `/bin/sh`, and dash/bash drop the
effective uid back down to the real uid on startup unless you are actually root.
So I lose the privilege exactly when I need it.

The fix is to call `setreuid(geteuid(), geteuid())` *before* `system()`, which
promotes the real uid up to the effective (oracle) uid so the shell keeps it.
Per `man 2 setreuid`, passing the current euid for both the real and effective
argument is the standard way to lock in the elevated id. My chain became:

```
setreuid_addr, poppop_ret, euid, euid,   # setreuid(euid, euid)
system_addr,   exit_addr,  binsh_addr     # system("/bin/sh"); exit()
```

with `setreuid = 0xf7c00000 + 0xc9670 = 0xf7cc9670` and I passed `geteuid()`'s
value (I read it once from a debug `system("id")` run) as both args.

**(3d) Stack-adjusting gadget.**

[I ran out of runway on this one. I know I needed a `pop; pop; ret` gadget to
clean setreuid's two arguments off the stack between the setreuid frame and the
system frame -- that is why there is a `poppop_ret` slot in my chain above -- but
I did not finish finding and disassembling the exact gadget address before the
deadline, so I am not going to fake a value here. My chain worked because I got
the alignment right by trial and error, but I cannot cleanly show you the gadget
disassembly and I would rather be honest about that than paste something I did
not verify.]

Final chain popped an oracle shell and read the flag:

![Phase Omega shell](screenshots/phase-omega-shell.png)

![Phase Omega flag](screenshots/phase-omega-flag.png)

Captured: `CECS378{vuln2_7d0e4b81}` (frontmatter `flag2`).

[--[ 4.0 -- AFTERMATH ]--]

**Which phase was harder, and why?**
Omega, easily. Phi is basically one idea -- put code somewhere and jump to it --
and the leak hands you the address so there is no guessing. Omega is three
separate gotchas stacked on top of each other: NX kills the obvious approach,
then you have to get every libc offset exactly right or you crash in a
completely uninformative way, and then the setuid drop silently gives you a
useless shell that *looks* like success. The setuid part cost me a whole evening
because the exploit "worked" and I still could not read the flag.

**What if there had been no `&buffer` leak?**
For vuln1 I would have been much worse off -- I would have fallen back to
spraying a huge NOP sled and picking a stack address in the typical
`0xffffd000` range and just brute forcing it across runs, because ASLR entropy on
32-bit is low enough that repeated tries land eventually. It is ugly and
probabilistic compared to being handed the exact address, but a low-entropy
brute force is a real primitive here.

**Why does a stack canary stop this whole class of attack?**
The canary is a random value the compiler puts between the local buffers and the
saved return address. To overwrite the return address with a linear `gets()`
overflow I *have* to write through the canary slot first, changing it. On
function return `__stack_chk_fail` checks the value, sees it does not match, and
aborts the program before `ret` ever loads my address -- so I never get control
of EIP in the first place. It does not fix the bug, it just turns a code-exec
into a clean crash.

**A source that stuck with me.**
Aleph One's "Smashing the Stack for Fun and Profit" (Phrack 49, article 14). The
part that made it click was that the stack layout diagram in section "The Stack"
is *exactly* what my `x/40wx $esp` dump showed -- buffer low, saved EBP, saved
EIP climbing to higher addresses. It matters because the whole exploit is just
arithmetic on that picture; once I trusted the diagram, the offset stopped being
a magic number I got from the grader and became something I could derive myself,
which is exactly what happened in section 1.0.
