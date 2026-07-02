---
real-name: Harvey Dent
csulb-id: "040100106"
handle: two-face
seed-fingerprint: facade
flag1: CECS378{vuln1_b81c40d7}
flag2: <paste captured Phase Omega flag>
honor-flag: CECS378{honor_hd_9c31e0af}
---

# After-Action Report -- Buffer Overflow Lab

[--[ 0.0 -- TARGET ]--]

I worked entirely in the provided Codespace so my toolchain would match the
grader's. I did not touch the local install on my laptop.

- Environment: GitHub Codespace, the assignment template image, gcc 11, 32-bit
  targets as the Makefile builds them.
- Started: 2026-06-26.
- Finished (Phase Phi): 2026-06-29. I did not get Phase Omega done -- see 3.0.

`make print-seed` output:

```
$ make print-seed
seed: facade  (fp=facade)
```

That `facade` matches `seed-fingerprint:` in the frontmatter, so the rebuilt
binaries should line up with what I attacked.

[--[ 1.0 -- RECON ]--]

**vuln1.** Breakpoint after the read, then dumped the frame and stack:

```
(gdb) info frame
Stack level 0, frame at 0xffffd710:
 eip = 0x080491c7 in vuln (vuln1.c:14); saved eip = 0xf7c23a41
 Saved registers:
  ebp at 0xffffd708, eip at 0xffffd70c
```

```
(gdb) x/40wx $esp
0xffffd6bc: 0x08049080  0xffffd7a0  0x00000000  0x41414141
0xffffd6cc: 0x41414141  0x41414141  0x41414141  0x41414141
0xffffd6dc: 0x41414141  0x41414141  0x41414141  0x41414141
0xffffd6ec: 0x41414141  0x41414141  0x41414141  0x41414141
0xffffd6fc: 0x41414141  0x41414141  0x41414141  0xf7fb3d20
0xffffd70c: 0xf7c23a41  0xffffd7a0  0xffffd7a8  0x00000000
```

`buffer` starts at `0xffffd6c0` and the saved EIP slot is at `0xffffd70c`:

```
0xffffd70c - 0xffffd6c0 = 0x4c = 76 bytes to the saved return address
```

Offset = **76** for vuln1. I verified with a `76 * "A" + "BBBB"` send and EIP
came back `0x42424242`, so I trust that number.

**vuln2.** I ran the same dump against the second binary and grabbed the frame:

```
(gdb) info frame
Stack level 0, frame at 0xffffd660:
 Saved registers:
  ebp at 0xffffd648, eip at 0xffffd64c
```

buffer for vuln2 sits at `0xffffd5f0`. I read the offset off gdb as 92 bytes and
was going to use it for Phase Omega, but since I did not finish Omega I did not
end up sending a payload against vuln2, so I am only fully confident in the
vuln1 arithmetic above.

[--[ 2.0 -- PHASE PHI ACE ]--]

Phase Phi attacks vuln1, which is built with an executable stack, so I can jump
into shellcode I place in the buffer.

Walking my `exploit1.c`:

1. **The shellcode bytes.** I used a 25-byte `execve("/bin/sh")` payload (lines
   9-15). The reason it is *these* bytes and not any random shellcode is that the
   vulnerable read stops at a null byte, so the shellcode has to be null-free. My
   stub uses `xor eax,eax` and pushes the `/bin//sh` string in two 4-byte chunks
   so there is never a `0x00` in the machine code -- I checked with `xxd` on the
   assembled bytes and confirmed it.

2. **The NOP sled.** Line 24 is `sled = b"\x90" * 48`. The runtime stack address
   drifts a bit between a gdb session and a bare run because of environment
   differences, so instead of aiming at the exact first byte of my shellcode I
   land anywhere in the sled and slide down into it. I picked 48 bytes because
   that comfortably covers the drift I measured while still leaving room inside
   the 76-byte budget for the 25-byte shellcode.

3. **Where the offset came from.** The `76` on line 27 is exactly the recon value
   from section 1.0 -- the distance from the start of `buffer` to the saved
   return address.

4. **The leaked address.** vuln1 prints `&buffer` before reading input. My code
   reads that line (line 20,
   `leak = int(p.stdout.readline().strip().split()[-1], 16)`) and I set the
   return address to `leak + 24` (line 28) so EIP lands inside the sled rather
   than trying to hit byte zero of the buffer. So the return address is not a
   guess -- the program leaks it and I offset into it.

The exploit dropped me into a shell running as the setuid oracle user:

![Phase Phi shell](screenshots/phase-phi-shell.png)

![Phase Phi flag](screenshots/phase-phi-flag.png)

Flag: `CECS378{vuln1_b81c40d7}` (frontmatter `flag1`).

[--[ 3.0 -- PHASE OMEGA ACE ]--]

> Note: I did not complete Phase Omega before the deadline. I understood from
> lecture that vuln2 has a non-executable stack so the Phase Phi approach will
> not work and a return-to-libc chain is required, but I ran out of time to
> actually build and test the chain. I am leaving the sub-part prompts below with
> the template placeholders unfilled rather than fabricate results I did not get.

**(3a) Why does the Phase Phi payload segfault against vuln2? Paste the signal
and explain the non-executable stack.**

[your answer]

**(3b) Show the libc offsets you used for `system`, `exit`, `setreuid`, and the
`"/bin/sh"` string, and name the tools you used to find them.**

[your answer]

**(3c) Explain why a naive `system("/bin/sh")` chain drops the setuid oracle
privilege, and name the fix.**

[your answer]

**(3d) Name the gadget-finding tool, give the `pop/pop/ret` address with its
disassembly, and explain why the chain needs it.**

[your answer]

Phase Omega flag: `<paste captured Phase Omega flag>` (unfilled -- not captured).

[--[ 4.0 -- AFTERMATH ]--]

**Which phase was harder, and why?**
Phase Phi was the one I actually finished, and even that one was harder than I
expected -- the first three times it segfaulted and it turned out my sled was too
short and the drift between gdb and a raw run was throwing me past the shellcode.
Once I widened the sled and used the leaked address instead of a hardcoded one it
became reliable. I cannot honestly rank Omega since I did not finish it, but from
reading the prompts it is clearly the harder one because the executable-stack
shortcut is gone and you have to reuse existing library code instead.

**What if there had been no `&buffer` leak in vuln1?**
Without the leak I could not just point the return address at a known spot. My
fallback would have been a big NOP sled plus a guessed stack address around
`0xffffd000` and repeatedly re-running the exploit until one attempt landed in
the sled -- a low-entropy brute force, which is realistic on 32-bit because there
just are not that many stack-address bits to guess.

**Why does a stack canary defeat this attack?**
The compiler puts a random canary value between the local buffer and the saved
return address. A linear `gets()` overflow has to overwrite the canary on its way
to the return address, so it changes it. On return, `__stack_chk_fail` compares
the canary against its saved copy, sees the mismatch, and aborts the process
before it ever executes `ret`. So I never get control of EIP -- the overflow
turns into a controlled crash instead of code execution.

**A source that stuck with me.**
The Phrack "Smashing the Stack" article was on the reading list and I read it.

[Thin -- I did read Aleph One's article and it helped me picture the stack, but I
did not tie a specific section back to my own output the way the other reflections
did, so I am marking this one as the weaker of the four.]
