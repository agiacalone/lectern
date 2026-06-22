# CECS 378 Demo — Question Bank

Synthetic exam-source bank for the lectern worked example. Validated + canonicalized
by `reg-qbank`. Question types: `mc`, `tf`, `fib` (also supports `code`). Each `id`
is `<type-letter><nn>`; non-`fib` types carry a `none` outcome. One `yaml` record
per fenced block (a bare mapping — `reg-qbank` skips list-form blocks).

```yaml
id: m01
type: mc
points: 2
section: I
difficulty: 1
stem: "Which property does a cryptographic hash function provide when it is infeasible to find two distinct inputs with the same digest?"
outcomes:
  - { key: a, text: "Preimage resistance", credited: false, points: 0 }
  - { key: b, text: "Collision resistance", credited: true, points: 2 }
  - { key: c, text: "Forward secrecy", credited: false, points: 0 }
  - { key: d, text: "Non-repudiation", credited: false, points: 0 }
  - { key: none, text: "No answer / multiple marks", credited: false, points: 0 }
```

```yaml
id: m02
type: mc
points: 2
section: II
difficulty: 2
stem: "A stack canary primarily defends against which class of attack?"
outcomes:
  - { key: a, text: "Stack buffer overflow overwriting the saved return address", credited: true, points: 2 }
  - { key: b, text: "SQL injection", credited: false, points: 0 }
  - { key: c, text: "Cross-site scripting", credited: false, points: 0 }
  - { key: d, text: "Padding-oracle attack", credited: false, points: 0 }
  - { key: none, text: "No answer / multiple marks", credited: false, points: 0 }
```

```yaml
id: t01
type: tf
points: 2
section: I
difficulty: 1
stem: "In RSA, a message encrypted with the recipient's public key can only be decrypted with the recipient's private key."
outcomes:
  - { key: "true", text: "True", credited: true, points: 2 }
  - { key: "false", text: "False", credited: false, points: 0 }
  - { key: none, text: "No answer / multiple marks", credited: false, points: 0 }
```

```yaml
id: f01
type: fib
points: 2
section: III
difficulty: 2
stem: "Access control where the resource owner sets permissions is _______; access control enforced by system policy the user cannot override is _______."
outcomes:
  - { key: b1, text: "discretionary (DAC)", credited: true, accept: ["discretionary", "dac"], points: 1 }
  - { key: b1-miss, text: "", credited: false, points: 0 }
  - { key: b2, text: "mandatory (MAC)", credited: true, accept: ["mandatory", "mac"], points: 1 }
  - { key: b2-miss, text: "", credited: false, points: 0 }
```
