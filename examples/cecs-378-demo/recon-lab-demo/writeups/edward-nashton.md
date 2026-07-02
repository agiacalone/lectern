---
real-name: Edward Nashton
csulb-id: "040100108"
handle: riddler
seed-fingerprint: e9e9e9
flag1: "CECS378{...}"
flag2: "CECS378{...}"
honor-flag: CECS378{i_did_my_own_w0rk_riddler_e9e9e9}
---

# After-Action Report -- Buffer Overflow Lab

[--[ 0.0 -- TARGET ]--]

- Course: CECS 378 -- Introduction to Computer Security Principles (Su26, section 01)
- Assignment: Lab 3 -- Buffer Overflow
- Handle: riddler
- Seed fingerprint: e9e9e9
- Environment: Ubuntu 22.04 course VM, x86-64, gdb 12.1
- ASLR: disabled per handout
- Started: 2026-06-26
- Submitted: 2026-06-28

Full disclosure up front: I put real time into this and I understand the theory, but **I could not get a shell to pop in either phase**. The autograder came back red for both flags. I'm turning in what I have with the reasoning I worked through, because I'd rather show my thinking than fake a flag I didn't earn. My binaries are stamped e9e9e9.

[--[ 1.0 -- RECON ]--]

Protections on the `ace` binary:

```
$ checksec --file=ace
    Arch:     amd64-64-little
    Stack:    No canary found
    NX:       NX disabled
    PIE:      No PIE
```

I ran a cyclic pattern under gdb to find the offset to the return address:

```
pwndbg> cyclic 150
aaaabaaacaaadaaaeaaafaaag...
pwndbg> run
Program received signal SIGSEGV, Segmentation fault.
pwndbg> x/wx $rsp
0xffffcf10: 0x6161616d
pwndbg> cyclic -l 0x6161616d
Found at offset 68
```

I got an offset of **68 bytes**. Honestly I'm not 100% sure this is right -- I saw the disassembly had a `sub rsp, 0x40` (64 bytes) and I expected 64 + 8 = 72, so getting 68 makes me think I either misread `$rsp` at the wrong moment or my pattern length was off. This might be part of why my exploit didn't land. I ran out of time to re-derive it cleanly.

[--[ 2.0 -- PHASE PHI ACE ]--]

The plan for Phase Phi was the textbook stack smash: overflow the buffer, overwrite the return address with a stack address pointing into a NOP sled, and land in execve shellcode.

```python
offset = 68            # (unsure -- see RECON)
payload  = b"A"*offset
payload += p64(0xffffcf30)   # guessed landing address
payload += b"\x90"*32
payload += shellcode_execve_binsh
```

When I ran it the program just segfaulted again instead of dropping to a shell:

```
$ (python3 phi.py; cat) | ./ace
Segmentation fault (core dumped)
```

**I could not get the shell to pop.** My best guesses at what went wrong: the return-address offset is off by a few bytes, or the stack address I hardcoded for the NOP sled landing zone was wrong (the address shifts a little depending on how the input is piped in vs. run interactively, and I think that moved my sled out from under RIP). I tried a couple of different landing addresses in the `0xffffcf00`--`0xffffcf40` range and widened the sled, but none of them caught. Because I never got a working exploit, I don't have a flag1 to submit.

[--[ 3.0 -- PHASE OMEGA ACE ]--]

I did not finish Phase Omega. I understand it needs a ret2libc/ROP approach because the stack is non-executable here, but since I couldn't even land the simpler Phase Phi shellcode exploit, I ran out of time before I could build the ROP chain. No flag2.

[--[ 4.0 -- AFTERMATH ]--]

**Reflection.** This lab humbled me. I can explain the buffer overflow on paper -- unbounded `gets()`, return address at a fixed offset, overwrite it to redirect execution -- and I could find the vulnerability and the offset in gdb. But turning that understanding into a working exploit is a completely different skill, and the gap between "I know why this works" and "I made this work" turned out to be huge. My exploit failed on the details: the exact offset and the exact stack address the sled lands on. Next time I'm going to lean harder on gdb to confirm the landing address at the moment of the return instead of guessing from the crash, and re-derive the offset carefully instead of trusting my first cyclic read. I'd rather turn this in honest and incomplete than pretend I got a shell I didn't get.
