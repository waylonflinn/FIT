# Pygments Fallback Test Document

This document contains fenced code blocks with info strings that are real-world
common but not necessarily recognised by pygments. The prototype should handle
each without crashing and label unknown strings as "Code".

## Known languages (should resolve)

```python
x = 1 + 2
print(x)
```

```javascript
const x = 1 + 2;
console.log(x);
```

```typescript
const x: number = 1 + 2;
```

```bash
echo "hello world"
```

```yaml
key: value
list:
  - item1
  - item2
```

```json
{"key": "value", "number": 42}
```

## Aliases (may or may not resolve)

```py
x = 1
```

```js
const x = 1;
```

```sh
ls -la
```

## Tricky strings (likely unknown — should fall back to "Code")

```output
Some command output here
nothing parseable
```

```console
$ ls -la
total 0
```

```text
Plain text block.
No language here.
```

```diff
- removed line
+ added line
  context line
```

```http
GET /api/v1/users HTTP/1.1
Host: example.com
Authorization: Bearer token123
```

```patch
--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
-old line
+new line
```

## Edge cases

```
Unannotated block — no info string at all.
```

``` 
Info string is only whitespace.
```

```PYTHON
Uppercase language name.
```
