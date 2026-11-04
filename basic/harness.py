"""HARNESS: run opencode on one task in a clean workspace, then judge the result.

    py basic/harness.py fpga_gain                      # one run, WITH skills + tools
    py basic/harness.py fpga_gain --without            # one run, plain agent (no skills, no tools)
    py basic/harness.py fpga_gain --compare --runs 3   # A/B: 3 runs without, 3 with, then a table
    py basic/harness.py fpga_gain --setup-only         # just build the workspace (no agent)
"""
import argparse, datetime, json, os, re, shutil, stat, subprocess, sys, time

BASIC = os.path.dirname(os.path.abspath(__file__))
PROMPT = "Read task.md and complete it. Work autonomously."
# Added to task.md only when skills + tools are present (so the "without" run is not told about them)
HELP = {
    "fpga_gain": "Help available: load the `verilog-fixed-point` skill before you start, and simulate "
                 "with the `run_sim` tool (short summary; full logs in `sim_logs/`).",
    "py_func": "Help available: load the `python-tdd` skill before you start, and run your tests "
               "with the `run_tests` tool.",
}


def load_config():
    """Tiny 'key: value  # comment' reader (no PyYAML needed)."""
    cfg = {}
    for line in open(os.path.join(BASIC, "config.yaml"), encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            cfg[k.strip()] = v.strip()
    cfg["context_limit"] = int(cfg["context_limit"])
    cfg["timeout_min"] = float(cfg["timeout_min"])
    return cfg


def native_path(p):
    """Git-Bash style '/c/foo' -> 'C:/foo' on Windows (native programs cannot read '/c/...')."""
    m = re.match(r"^/([a-zA-Z])/(.*)", p)
    return f"{m.group(1).upper()}:/{m.group(2)}" if os.name == "nt" and m else p


def tool_env(cfg):
    """Environment variables read by tools/*.ts and the judges."""
    return {"IVERILOG_DIR": native_path(cfg.get("iverilog_dir", "")),
            "PYTHON_CMD": cfg.get("python_cmd", "python3")}


def rmtree(path):
    def onerr(fn, p, _):
        os.chmod(p, stat.S_IWRITE)
        fn(p)
    shutil.rmtree(path, onerror=onerr)


def setup_workspace(task, cfg, with_help=True):
    """Fresh workspace = task's agent/ files (+ .opencode/{skills,tools} when with_help) + opencode.json."""
    ws = os.path.abspath(os.path.join(BASIC, cfg["workspace"]))
    if ws == BASIC or BASIC.startswith(ws + os.sep) or ws.startswith(BASIC + os.sep):
        sys.exit(f"refusing to use workspace {ws}: it must be outside basic/ and not contain it")
    if os.path.isdir(ws):
        rmtree(ws)
    shutil.copytree(os.path.join(BASIC, "tasks", task, "agent"), ws)        # only agent/, never hidden/
    if with_help:
        shutil.copytree(os.path.join(BASIC, "skills"), os.path.join(ws, ".opencode", "skills"))
        shutil.copytree(os.path.join(BASIC, "tools"), os.path.join(ws, ".opencode", "tools"))
    tm = os.path.join(ws, "task.md")
    text = open(tm, encoding="utf-8").read().replace("{HELP}", HELP.get(task, "") if with_help else "")
    open(tm, "w", encoding="utf-8").write(text)
    model = cfg["model"]
    oc = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {"local": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Local model",
            "options": {"baseURL": cfg["base_url"]},
            "models": {model: {"name": model, "limit": {"context": cfg["context_limit"], "output": 8192}}},
        }},
        "model": f"local/{model}",
        "permission": {"*": "allow", "external_directory": "deny", "doom_loop": "deny",
                       "webfetch": "deny", "websearch": "deny"},
    }
    with open(os.path.join(ws, "opencode.json"), "w") as f:
        json.dump(oc, f, indent=2)
    return ws


def kill_tree(p):
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    else:
        p.kill()


def opencode(cfg):
    """(path, version) of the opencode CLI: config opencode_cmd, else PATH."""
    exe = cfg.get("opencode_cmd") or shutil.which("opencode")
    if not exe or not (os.path.isfile(exe) or shutil.which(exe)):
        return None, ""
    return exe, subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip()


def tools_supported(ver):
    # .opencode/tools/*.ts is the opencode 1.x custom-tool format; 2.x only loads tools from plugins
    return bool(re.match(r"^(v)?1\.", ver.split()[-1] if ver else ""))


def run_agent(ws, cfg, log_path):
    exe, ver = opencode(cfg)
    if not exe:
        return None, "opencode not found (set opencode_cmd in config.yaml or put it on PATH)"
    # opencode 1.x has no --standalone (it uses --dir); 2.x runs a private server with --standalone
    flags = ["--dir", ws] if ver.startswith("1.") else ["--standalone"]
    cmd = [exe, "run", *flags, "--auto", "-m", f"local/{cfg['model']}", PROMPT]
    # own opencode config/data/state per run: personal settings never leak in, every run starts clean
    home = os.path.join(os.path.dirname(log_path), "opencode_home")
    xdg = {f"XDG_{k}_HOME": os.path.join(home, k.lower()) for k in ("CONFIG", "DATA", "STATE")}
    for d in xdg.values():
        os.makedirs(d, exist_ok=True)
    # iverilog/python on PATH in BOTH modes: the agent can always simulate from the shell;
    # "with" only adds know-how (skill) and a convenient action (tool)
    tenv = tool_env(cfg)
    path = os.pathsep.join(x for x in (tenv["IVERILOG_DIR"], os.environ.get("PATH", "")) if x)
    env = dict(os.environ, PWD=ws, OPENCODE_CONFIG=os.path.join(ws, "opencode.json"), PATH=path, **xdg, **tenv)
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        p = subprocess.Popen(cmd, cwd=ws, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            p.wait(timeout=cfg["timeout_min"] * 60)
            note = f"exit {p.returncode}"
        except subprocess.TimeoutExpired:
            kill_tree(p)
            note = f"timed out after {cfg['timeout_min']:g} min"
    return (time.time() - t0) / 60, note


def judge(task, ws, cfg):
    env = dict(os.environ, **tool_env(cfg))
    r = subprocess.run([sys.executable, os.path.join(BASIC, "tasks", task, "judge.py"), ws],
                       env=env, capture_output=True, text=True, timeout=600)
    line = (r.stdout.strip().splitlines() or [r.stderr.strip()[-200:] or "judge printed nothing"])[-1]
    passed = r.returncode == 0
    reason = re.sub(r"^(PASS|FAIL):\s*", "", line)
    m = re.search(r"SCORE:\s*([\d.]+)%", r.stdout)
    return passed, reason, float(m.group(1)) if m else 0.0


def one_run(task, cfg, with_help):
    """Build a fresh workspace, run the agent, judge. Returns the result dict."""
    mode = "with" if with_help else "without"
    ws = setup_workspace(task, cfg, with_help)
    run_dir = os.path.join(os.path.dirname(ws), "basic_runs",
                           datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{task}_{mode}")
    os.makedirs(run_dir)
    minutes, note = run_agent(ws, cfg, os.path.join(run_dir, "agent.log"))
    if minutes is None:
        sys.exit(note)
    passed, reason, score = judge(task, ws, cfg)
    exe, ver = opencode(cfg)
    res = {"task": task, "mode": mode, "passed": passed, "score": score, "reason": reason,
           "opencode": ver, "tools_loaded": with_help and tools_supported(ver),
           "agent_minutes": round(minutes, 2), "agent_note": note, "model": cfg["model"]}
    # keep what the agent produced, for showing afterwards
    shutil.copytree(ws, os.path.join(run_dir, "workspace"), ignore=shutil.ignore_patterns(".opencode", "node_modules"))
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print(f"{task} [{mode} skills+tools]: {'PASS' if passed else 'FAIL'} (score {score:.0f}%) — {reason} "
          f"(agent {minutes:.1f} min)", flush=True)
    return res


def compare(task, cfg, runs):
    """A/B: same task, same model, same hidden judge; only the skills + tools differ."""
    exe, ver = opencode(cfg)
    if not tools_supported(ver):
        sys.exit(f"opencode '{ver}' does not load .opencode/tools/*.ts (that is the 1.x format), so the "
                 "'with' side would get the skill but no tool. Use opencode 1.x (set opencode_cmd).")
    out = {"without": [], "with": []}
    for i in range(runs):                       # interleave, so time-of-day effects hit both equally
        for mode in ("without", "with"):
            out[mode].append(one_run(task, cfg, mode == "with"))
    print()
    print(f"A/B result for '{task}' with {cfg['model']} ({runs} runs each)")
    print(f"{'':24}{'passed':>10}{'median score':>15}{'coding time':>14}")
    for mode, label in (("without", "plain agent"), ("with", "agent + skill + tool")):
        rs = out[mode]
        med = lambda k: sorted(r[k] for r in rs)[len(rs) // 2]
        print(f"{label:24}{sum(r['passed'] for r in rs):>6} of {len(rs):<3}{med('score'):>12.0f}%"
              f"{med('agent_minutes'):>11.1f} min")
    print("score = % of hidden test samples/cases the final design gets right (same hidden judge for both)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--setup-only", action="store_true", help="build the workspace, do not run the agent")
    ap.add_argument("--without", action="store_true", help="plain agent: no skills, no custom tools")
    ap.add_argument("--compare", action="store_true", help="A/B: --runs runs without, then with")
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    cfg = load_config()
    if not os.path.isdir(os.path.join(BASIC, "tasks", a.task)):
        sys.exit(f"unknown task '{a.task}'; available: {sorted(os.listdir(os.path.join(BASIC, 'tasks')))}")
    exe, ver = opencode(cfg)
    if not a.without and not a.setup_only and not tools_supported(ver):
        print(f"WARNING: opencode '{ver}' will not load the custom tools (1.x format); skills still work.")
    if a.setup_only:
        print(f"workspace ready: {setup_workspace(a.task, cfg, not a.without)}")
    elif a.compare:
        compare(a.task, cfg, a.runs)
    else:
        one_run(a.task, cfg, not a.without)


if __name__ == "__main__":
    main()
