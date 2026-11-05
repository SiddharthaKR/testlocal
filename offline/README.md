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

## opencode 2.2.5 (Linux x64)

`opencode-2.2.5-linux-x64.tgz.part00` + `.part01`: the official npm package `@opencode/cli-linux-x64@2.2.5`
(repo anomalyco/opencode, MIT), split in two because GitHub rejects files over 100 MB.
SHA-256 of the joined file: `92690eee07a680d3cb760ca02ba43878de9eab1b4e5d5dfae8795518c53628f4`

```bash
cat offline/opencode-2.2.5-linux-x64.tgz.part* > /tmp/opencode-2.2.5.tgz
sha256sum /tmp/opencode-2.2.5.tgz                       # must match the hash above
mkdir -p ~/opencode2 && tar xzf /tmp/opencode-2.2.5.tgz -C ~/opencode2
~/opencode2/package/bin/opencode --version              # 2.2.5
```
Warning: 2.x does NOT load `.opencode/tools/*.ts` custom tools. The basic demo's `run_sim`/`run_tests`
won't exist and `basic/harness.py --compare` refuses to run; skills and the full harness still work.
To keep both versions, call 2.x by its full path, or set `opencode_cmd` in `basic/config.yaml`.
