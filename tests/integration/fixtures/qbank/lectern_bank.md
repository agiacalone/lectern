# Demo bank (Lectern format)

```yaml
id: m01
type: mc
points: 2
stem: "Which key encrypts an RSA message for a recipient?"
outcomes:
  - { key: a, text: "The sender's private key", credited: false, points: 0 }
  - { key: b, text: "The recipient's public key", credited: true, points: 2 }
  - { key: c, text: "A shared session key", credited: false, points: 0 }
  - { key: none, text: "No answer / multiple marks", credited: false, points: 0 }
```

```yaml
id: t01
type: tf
points: 2
stem: "AES is a symmetric cipher."
outcomes:
  - { key: "true", text: "True", credited: true, points: 2 }
  - { key: "false", text: "False", credited: false, points: 0 }
  - { key: none, text: "No answer / multiple marks", credited: false, points: 0 }
```
