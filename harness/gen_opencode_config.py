"""Generate config/opencode.json from config/env.yaml (edit env.yaml only).

Permissions keep the agent inside its workspace and away from hidden material
(judges, reference solutions, harness). Last matching rule wins in opencode, so
catch-alls come first. Leak detection (harness/judge/leak_check.py) backs this up.
"""
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
env = yaml.safe_load((ROOT / "config" / "env.yaml").read_text())

HIDDEN = ["*harness*", "*judge*", "*ref_solution*", "*vendor*", "*ai_demo*", "*runs*",
          "*selftest*", "*.claude*", "*opencode.json*"]


def rules(default, deny=HIDDEN):
    r = {"*": default}
    r.update({p: "deny" for p in deny})
    return r


cfg = {
    "$schema": "https://opencode.ai/config.json",
    "provider": {
        "local": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Local via proxy",
            "options": {"baseURL": f"http://localhost:{env['proxy_port']}/v1"},
            # limit lets opencode compact the history itself instead of Ollama silently truncating
            "models": {env["model"]: {"name": env["model"],
                                      "limit": {"context": int(env["context_limit"]), "output": 8192}}},
        }
    },
    "model": f"local/{env['model']}",
    "permission": {
        "*": "allow",
        "external_directory": "deny",       # nothing outside the workspace
        "read": rules("allow"),
        "edit": rules("allow"),
        "glob": rules("allow"),
        "grep": rules("allow"),
        # bash: also block parent-directory escapes and absolute-path listing
        # (best effort: a determined shell one-liner can still escape; the canary
        # leak check is the backstop)
        "bash": rules("allow", HIDDEN + ["*..*", "*/c/*", "*C:*", "*c:*", "*~*", "*$HOME*", "*USERPROFILE*",
                                         "*/home/*", "*/tmp/*", "*/Users/*", "find /*", "ls /*",
                                         "*getcwd*", "*chdir*", "*abspath*", "*realpath*", "*.parent*",
                                         "*dirname*", "*pushd*", "*Get-ChildItem*", "*os.walk*", "*listdir*",
                                         # the harness repo is public: no fetching it (or anything) from the net
                                         "*github*", "*curl*", "*wget*", "*Invoke-WebRequest*", "*urllib*",
                                         "*requests.get*", "*git clone*", "*git fetch*", "*git pull*",
                                         "*git remote*", "*http://*", "*https://*"]),
        "webfetch": "deny",
        "websearch": "deny",
        "task": "deny",
    },
}
out = ROOT / "config" / "opencode.json"
out.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"wrote {out}")
