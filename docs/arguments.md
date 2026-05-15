# Argument Substitution Guide

> How to make aliases accept and use arguments.

`qwik` supports two execution modes for aliases: **append** and **template**. The mode is automatically detected by whether the command contains any `{…}` placeholder.

---

## Append Mode (default)

When a command has **no placeholders**, extra arguments typed after the alias name are simply appended with safe quoting.

### Example

```bash
qwik add gs "git status"
gs --short              # → git status --short
```

Any arguments after the alias name are shell-quoted and appended:

```bash
alias-with-spaces "two words"
# → the original command + 'two words' (safely quoted)
```

---

## Template Mode

When a command contains `{1}`, `{@}`, `{*}`, or `{1:-default}`, `qwik` switches into **template mode**.

In template mode, placeholders are substituted with the provided runtime arguments at their exact positions. Any arguments *not* consumed by placeholders are still appended after the command using safe quoting.

---

## Placeholder Reference

| Placeholder | What it means | Example input | Result |
|---|---|---|---|
| `{1}` | 1st positional argument | `gco main` | `main` |
| `{2}` | 2nd positional argument | `gcm feat "add login"` | `add login` |
| `{3}`, `{4}`… | Nth positional argument | — | — |
| `{@}` | All arguments joined with spaces | `gc-chore init version` | `init version` |
| `{*}` | All arguments as a single quoted string | `note hello world` | `'hello world'` |
| `{1:-main}` | 1st arg, or `main` if not provided | `gpo` (no args) | `main` |
| `{2:-patch}` | 2nd arg, or `patch` if not provided | `gvt minor` | `patch` |

---

## Practical Examples

### Git shortcuts

```bash
# Checkout a branch
qwik add gco "git checkout {1}"
gco main
  # → git checkout main

# Commit with type and message
qwik add gcm 'git commit -m "{1}: {2}"'
gcm feat "add login form"
  # → git commit -m "feat: add login form"

# Push to origin with optional branch (defaults to main)
qwik add gpo "git push origin {1:-main}"
gpo
  # → git push origin main
gpo feature/x
  # → git push origin feature/x

# Conventional commit - chore
qwik add gc-chore 'git commit -m "chore: {@}"'
gc-chore bump version
  # → git commit -m "chore: bump version"

# Conventional commit - with default scope
qwik add gcf 'git commit -m "feat({1:-core}): {@}"'
gcf api "add auth endpoint"
  # → git commit -m "feat(api): add auth endpoint"
gcf "fix typo"
  # → git commit -m "feat(core): fix typo"
```

### Kubernetes shortcuts

```bash
# Run kubectl with a subcommand
qwik add k "kubectl {1}"
k get pods -n kube-system
  # → kubectl get pods -n kube-system

# Get pods in a namespace (default: default)
qwik add kgp "kubectl get pods -n {1:-default}"
kgp
  # → kubectl get pods -n default
kgp kube-system
  # → kubectl get pods -n kube-system

# Describe anything
qwik add kd "kubectl describe {1} {2}"
pd pod my-app-7f4d9
  # → kubectl describe pod my-app-7f4d9
```

### Docker shortcuts

```bash
# Compose up with optional services
qwik add dcu "docker compose up {@:-all}"
dcu
  # → docker compose up all
dcu db web
  # → docker compose up db web

# Run a container
qwik add dr "docker run {1} {@}"
dr --rm -it ubuntu
  # → docker run --rm -it ubuntu
```

### General utility

```bash
# Make a directory and cd into it
qwik add mkcd 'mkdir -p {1} && cd {1}'
mkcd src/components
  # → mkdir -p src/components && cd src/components

# Quick serve directory
qwik add serve "python3 -m http.server {1:-8080}"
serve
  # → python3 -m http.server 8080
serve 3000
  # → python3 -m http.server 3000

# Search history
qwik add hsg "history | grep {1}"
hsg git
  # → history | grep git

# Copy with progress
qwik add cpv "rsync -ah --progress {1} {2}"
cpv ~/Downloads/bigfile.zip /mnt/backup/
  # → rsync -ah --progress ~/Downloads/bigfile.zip /mnt/backup/
```

---

## How Surplus Arguments Work

When you use a template alias with more arguments than placeholders consume, the extra ones are safely appended.

```bash
qwik add k "kubectl {1}"

# {1} gets 'get', then 'pods -n kube-system' is appended
k get pods -n kube-system
  # → kubectl get pods -n kube-system
```

If all arguments are consumed by `{@}` or `{*}`, nothing is appended:

```bash
qwik add gc-chore 'git commit -m "chore: {@}"'
gc-chore fix typo
  # → git commit -m "chore: fix typo"
  #   (nothing extra appended because {@} consumed both args)
```

---

## Escaping and Safety

### Quoting behavior

- Plain args are passed through `shlex.quote()` to handle spaces, quotes, and shell metacharacters safely
- `{*}` wraps all arguments as a single shell-quoted string
- `{@}` joins args with spaces (no extra quoting beyond join)

### Shell metacharacters

If the expanded command contains shell metacharacters (`;`, `|`, `&&`, `||`, `>`, `<`, `~`, `*`, `?`, `$()`), `qwik` automatically switches to `shell=True` execution. Otherwise it uses a safer argv list.

```bash
qwik add mkcd 'mkdir -p {1} && cd {1}'
# Contains && → runs via shell=True
```

---

## Validation and Error Messages

### At add time

`qwik` validates placeholders when you create an alias:

```bash
qwik add bad "echo {0}"
# ✗ Error: {0} is not valid. Positional placeholders must be 1-based ({1}, {2}, ...).
```

### At runtime

If a required positional is missing, a clear error is shown:

```bash
qwik add gco "git checkout {1}"
gco
# ✗ Error: Missing argument 1 for alias: "git checkout {1}" (received 0 argument(s))
```

Use `{1:-default}` to avoid this by providing a fallback:

```bash
qwik add gco "git checkout {1:-main}"
gco
# → git checkout main      (no error — falls back to 'main')
```

### Validation ensures you don't forget args

Unlike raw shell aliases where missing `$1` silently becomes empty, `qwik` tells you exactly what's wrong:

```bash
# Raw shell alias (subtle bug):
alias gco='git checkout $1'
gco
# → git checkout           # silently wrong!

# qwik alias (clear error):
gco
# → Missing argument 1 for alias: "git checkout {1}" (received 0 argument(s))
```

---

## Tips

1. **Use `{1:-default}` for optional args** — it provides a fallback and skips runtime validation
2. **Use `{@}` for "the rest"** — convenient when the number of args is variable
3. **Use `{*}` when you need a single string** — useful for messages, commit bodies, etc.
4. **You can mix placeholders** — e.g., `"echo {1} and {@}"` (but be mindful of what gets duplicated)
5. **Defaults can be empty** — `{1:-}` falls back to an empty string instead of erroring
