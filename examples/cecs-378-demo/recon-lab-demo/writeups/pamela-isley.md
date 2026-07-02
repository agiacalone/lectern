---
real-name: Pamela Isley
csulb-id: "040100107"
handle: poison-ivy
seed-fingerprint: 0f00ba
flag1: CECS378{vuln1_2c6ad9f0}
flag2: <paste captured Phase Omega flag>
honor-flag: CECS378{honor_pi_44be7102}
---

# After-Action Report -- Buffer Overflow Lab

[--[ 0.0 -- TARGET ]--]

I did this in the Codespace off the template so the binaries would match what
the grader rebuilds. I did not build anything on my own machine.

- Environment: GitHub Codespace, template image, gcc, 32-bit binaries from the
  provided Makefile.
- Started: 2026-06-27.
- Finished Phase Phi: 2026-06-30. I did not get Phase Omega working.

Seed line:

```
$ make print-seed
seed: 0f00ba  (fp=0f00ba)
```

`0f00ba` is the same value as `seed-fingerprint:` in my frontmatter, so the
grader's rebuild should match my binaries.

[--[ 1.0 -- RECON ]--]

**vuln1.** I set a breakpoint inside `vuln` after the input read and looked at
the frame and the stack.

```
(gdb) info frame
Stack level 0, frame at 0xffffd680:
 eip = 0x080491c7 in vuln (vuln1.c:14); saved eip = 0xf7c23a41
 Saved registers:
  ebp at 0xffffd678, eip at 0xffffd67c
```

```
(gdb) x/40wx $esp
0xffffd62c: 0x08049080  0xffffd710  0x00000000  0x41414141
0xffffd63c: 0x41414141  0x41414141  0x41414141  0x41414141
0xffffd64c: 0x41414141  0x41414141  0x41414141  0x41414141
0xffffd65c: 0x41414141  0x41414141  0x41414141  0x41414141
0xffffd66c: 0x41414141  0x41414141  0x41414141  0xf7fb3d20
0xffffd67c: 0xf7c23a41  0xffffd710  0xffffd718  0x00000000
```

The buffer is the run of `0x41414141` starting at `0xffffd630`, and gdb reports
the saved EIP at `0xffffd67c`. Working from that, the offset to the return
address is **76 bytes**. I checked it by sending 76 `A`s followed by `BBBB` and
EIP came back as `0x42424242`, so 76 is the number I used for the rest of the
lab.

I only did recon on vuln1 -- I did not get far enough into Phase Omega to need
vuln2's frame, so I did not dump it.

[--[ 2.0 -- PHASE PHI ACE ]--]

Phase Phi is the shellcode attack on vuln1, which has an executable stack, so I
can run bytes I place in the buffer.

Walking my `exploit1.c`:

1. **The shellcode bytes.** I used a 25-byte `execve("/bin/sh")` shellcode
   (lines 7-13 of exploit1.c). The reason it is these exact bytes is that the
   input is read as a string, so any `0x00` byte would cut my payload off early.
   This shellcode is null-free -- it zeroes registers with `xor` instead of
   moving in literal zeros, and it pushes `/bin//sh` as two words -- so nothing
   in it truncates. I disassembled it back with `objdump` to be sure there were
   no zero bytes.

2. **The NOP sled.** I put a run of `0x90` NOPs in front of the shellcode (line
   19, `sled = b"\x90" * 40`). Because the exact stack address wobbles a little
   between gdb and a normal run, I do not need to hit the first byte of my
   shellcode exactly -- if EIP lands anywhere in the NOPs it just slides down
   into the real code. 40 bytes was enough to absorb the drift and still fit the
   shellcode in the 76-byte space.

3. **Where the offset came from.** The 76 in my payload construction (line 22)
   is the recon number from section 1.0 -- start of buffer to saved return
   address.

4. **The leaked address.** vuln1 prints the address of `buffer` before it reads
   input, and my exploit reads that line (line 16,
   `leak = int(p.stdout.readline().split()[-1], 16)`) and uses it to set the
   return address a little bit into the sled (`ret = pack("<I", leak + 16)`).
   That way I am aiming at an address the program told me instead of guessing.

It dropped me into an oracle shell and I read the flag:

![Phase Phi shell](screenshots/phase-phi-shell.png)

![Phase Phi flag](screenshots/phase-phi-flag.png)

Flag: `CECS378{vuln1_2c6ad9f0}` (frontmatter `flag1`).

[--[ 3.0 -- PHASE OMEGA ACE ]--]

> Note: I was not able to finish Phase Omega. I understand the general idea --
> vuln2's stack is not executable, so the Phase Phi shellcode approach will not
> run and you have to return into libc instead -- but I could not get a working
> chain together before the deadline. I am leaving the sub-prompts with their
> template placeholders instead of writing answers I did not actually produce.

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

Phase Omega flag: `<paste captured Phase Omega flag>` (not captured).

[--[ 4.0 -- AFTERMATH ]--]

**Which phase was harder, and why?**
Phase Phi is the only one I got working, and it still fought me -- my first
attempts crashed because I had hardcoded a stack address from gdb and it did not
match the real run. Switching to the leaked `&buffer` address fixed it. I did not
finish Omega, but even reading its prompts it is obviously the harder half,
because losing the executable stack means you cannot just run your own code and
you have to stitch together calls into existing library functions.

**What if there had been no `&buffer` leak?**
Without the leak I would have had to guess the stack address. My plan would have
been a much bigger NOP sled and a guessed address in the usual `0xffffd000`
neighborhood, re-running the exploit over and over until a run happened to land
in the sled. On 32-bit there are few enough address bits that this kind of
low-entropy brute force actually succeeds in a reasonable number of tries.

**Why does a stack canary stop this?**
There is a random canary word placed between the buffer and the saved return
address. My overflow writes straight through everything up to the return address,
so it has to clobber the canary. When the function returns, `__stack_chk_fail`
notices the canary no longer matches and aborts the program before `ret` runs,
so I never actually get to redirect EIP -- the attack becomes a crash instead of
a shell.

**A source that stuck with me.**
I looked at the "Smashing the Stack" reading.

[Thin -- I skimmed the Phrack article but I did not connect a specific part of it
to my own work, so this reflection is weaker than the other three.]
