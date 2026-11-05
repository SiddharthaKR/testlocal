# Offline opencode install (Linux x64)

`opencode-1.19.5-linux-x64.tar.gz`: the opencode CLI, downloaded unchanged from the official release
https://github.com/anomalyco/opencode/releases/tag/v1.19.5 (MIT licence).
SHA-256: `588310a336fa3b9df36b3f0225b26f679d453efaad0cf3d66c3651ef3ec1647a`

Install:
```bash
sha256sum offline/opencode-1.19.5-linux-x64.tar.gz      # must match the hash above
mkdir -p ~/.local/bin && tar xzf offline/opencode-1.19.5-linux-x64.tar.gz -C ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"                     # add to ~/.bashrc to keep it
opencode --version                                       # 1.19.5
```
If the server CPU is old (no AVX2) and opencode crashes with "illegal instruction", use the
`opencode-linux-x64-baseline.tar.gz` asset from the same release instead.
Tested in this repo on 1.17.15; 1.19.5 is the same 1.x line (custom tools load), but run
`python3 basic/selftest.py` and one `basic/harness.py py_func` run to confirm.
