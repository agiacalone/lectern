---
type: feedback-log
tags: [feedback-log, grading, private]
visibility: private
icon: LiMessageSquareText
iconColor: var(--text-normal)
---
# Lab 3 — Buffer Overflow (demo) · Feedback Delivered to Students
*CECS 378 · su26 · §01 — verbatim record*

### Bruce Wayne — 100/100
*github: `bruce-wayne` · Auto 70/70 · Writeup 30/30 · UNSIGNED · PR - · main -*

> Outstanding after-action report. RECON derives the offset from your own leaked buffer/saved-EIP pair; Phase Phi ties every shellcode stage to a reason; Phase Omega is complete end-to-end — libc base from the printf leak, the setreuid privilege fix with a man-page cite, and a real pop/pop/ret gadget with disassembly. Nothing to add.

### Barbara Gordon — 99/100
*github: `barbara-gordon` · Auto 70/70 · Writeup 29/30 · UNSIGNED · PR - · main -*

> Excellent, mechanism-first write-up. Both phases are explained at the byte level and your reflections are concrete. To reach full on Phase Omega, show the numeric libc offsets your commands returned rather than describing them. Great work.

### Dick Grayson — 97/100
*github: `dick-grayson` · Auto 70/70 · Writeup 27/30 · UNSIGNED · PR - · main -*

> Strong report. Phase Phi is exact and your Omega ret2libc chain is clearly reasoned. Two gaps: paste vuln2's own gdb output in RECON, and add the pop/pop/ret disassembly in Phase Omega. Well done.

### Kate Kane — 96/100
*github: `kate-kane` · Auto 70/70 · Writeup 26/30 · UNSIGNED · PR - · main -*

> Nice work — both phases land and your leak-then-pwn explanation is clear. For full marks, paste both binaries' gdb output and add the setreuid man-page citation in Phase Omega.

### Harvey Dent — 78/100
*github: `harvey-dent` · Auto 60/70 · Writeup 18/30 · UNSIGNED · PR - · main -*

> Your Phase Phi walkthrough is solid — the sub-esp guard, the setreuid privilege fix, and the NOP-sled sizing are all here. Phase Omega was left as template placeholders; even without a working exploit you earn most of those points by writing up the NX fail-analysis, the libc offsets, and the pop/pop/ret gadget. Give the ret2libc walkthrough a try.

### Pamela Isley — 77/100
*github: `pamela-isley` · Auto 60/70 · Writeup 17/30 · UNSIGNED · PR - · main -*

> Good Phase Phi engagement. Two things to tighten: RECON needs the explicit offset subtraction and both binaries' gdb output, and Phase Omega is unfilled — the ret2libc mechanism is worth writing up even without a passing exploit.

### Oswald Cobblepot — 75/100
*github: `oswald-cobblepot` · Auto 60/70 · Writeup 15/30 · UNSIGNED · PR - · main -*

> Your Phase Phi exploit passed, but the walkthrough is generic — tie it to specific lines of your own exploit1.c. Phase Omega is left as placeholders; completing the ret2libc write-up is the biggest available gain. Flesh out the reflections too.

### Jason Todd — 70/100
*github: `jason-todd` · Auto 70/70 · Writeup 0/30 · UNSIGNED · PR - · main -*

> _no comment_

### Edward Nashton — 12/100
*github: `edward-nashton` · Auto 0/70 · Writeup 12/30 · UNSIGNED · PR - · main -*

> Right now neither exploit lands in the autograder, but your RECON and Phase Phi reasoning show real understanding. Get a working shell on vuln1 first, then fill the Phase Omega section. Please come to office hours — there's credit waiting once the exploits work and the sections are filled.

