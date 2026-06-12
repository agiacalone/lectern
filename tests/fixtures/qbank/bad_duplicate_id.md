# Bad — duplicate id across the bank

```yaml
id: dup-01
topic: test
type: mc
points: 2
stem: First question.
outcomes:
  - {key: a, text: "Option A", credited: true, feedback: ""}
  - {key: b, text: "Option B", credited: false, feedback: ""}
  - {key: none, text: "No answer", credited: false, feedback: ""}
```

```yaml
id: dup-01
topic: test
type: mc
points: 2
stem: Second question with the same id.
outcomes:
  - {key: a, text: "Option A", credited: true, feedback: ""}
  - {key: b, text: "Option B", credited: false, feedback: ""}
  - {key: none, text: "No answer", credited: false, feedback: ""}
```
