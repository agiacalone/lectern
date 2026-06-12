# Bad — fib blank with empty accept list

```yaml
id: bad-fib-01
topic: test
type: fib
points: 2
stem: "Fill in the blank: A ___ is a self-propagating program."
outcomes:
  - {key: b1, text: "worm", credited: true, feedback: "Correct.", accept: []}
  - {key: b1-miss, text: "", credited: false, feedback: ""}
```
