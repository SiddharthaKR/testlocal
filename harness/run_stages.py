"""
Stages 3-7 of a demo run (called by run_demo.sh after the workspace is ready):
proxy -> agent (opencode) -> collect -> judge -> QoR -> leak check -> report.

  run_stages.py <run_dir> <workspace> <track> [--assist] [--interactive]

Updates <run_dir>/run_meta.json with timings:
  wall_seconds    time the agent worked (what the report compares to an engineer)
  total_seconds   whole pipeline incl. judging
  llm_seconds     time inside model requests (from the proxy log)
  vivado_seconds  Vivado time (agent tool calls + judge QoR), 0 if no Vivado
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import yaml

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parent
ENV = yaml.safe_load((ROOT / "config" / "env.yaml").read_text())
PY = sys.executable           # real interpreter (not the py launcher) so terminate() hits it
RTL_REL = Path("pyrpl") / str(ENV["pyrpl_rtl"])
PROMPT = ("Read AGENTS.md and tasks/{t}/task.md, then complete the task described there. "
          "Work autonomously until it is done; do not ask me questions.")


def log(msg):
    print(f"[run_demo] {msg}", flush=True)


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_proxy(run):
    port = int(ENV["proxy_port"])
    if port_open(port):
        raise SystemExit(f"port {port} already in use (another proxy running?)")
    f = open(run / "proxy.log", "w")
    p = subprocess.Popen([PY, str(HARNESS / "proxy" / "llm_proxy.py"), "--run-dir", str(run)],
                         stdout=f, stderr=subprocess.STDOUT)
    for _ in range(50):
        if port_open(port):
            return p
        if p.poll() is not None:
            raise SystemExit(f"proxy exited early, see {run / 'proxy.log'}")
        time.sleep(0.2)
    p.terminate()
    raise SystemExit("proxy did not come up")


def check_upstream():
    try:
        urllib.request.urlopen(str(ENV["upstream_url"]).rstrip("/") + "/models", timeout=5).read()
        return True
    except OSError as e:
        log(f"WARNING: upstream {ENV['upstream_url']} not reachable: {e}")
        return False


def run_agent(ws, track, interactive, run):
    exe = shutil.which("opencode")
    if not exe:
        raise SystemExit("opencode not found on PATH")
    # opencode takes its project dir from PWD (inherited from the calling shell = the repo),
    # not from the process cwd, so set both to the workspace
    env = dict(os.environ, OPENCODE_CONFIG=str(ROOT / "config" / "opencode.json"), PWD=str(ws))
    model = f"local/{ENV['model']}"
    t0 = time.time()
    if interactive:
        log("interactive: opencode opens in the workspace; quit it when the agent is done")
        rc = subprocess.call([exe, "--auto", str(ws)], cwd=ws, env=env)   # model comes from opencode.json
        timed_out = False
    else:
        timeout = float(ENV.get("agent_timeout_min", 40)) * 60
        with open(run / "agent_console.log", "w", encoding="utf-8", errors="replace") as f:
            p = subprocess.Popen([exe, "run", "--standalone", "--auto", "-m", model, "--title", run.name,
                                  PROMPT.format(t=track)], cwd=ws, env=env, stdout=f, stderr=subprocess.STDOUT)
            try:
                rc = p.wait(timeout=timeout); timed_out = False
            except subprocess.TimeoutExpired:
                log(f"agent timed out after {timeout / 60:.0f} min; stopping it")
                p.kill(); rc = -1; timed_out = True
    return time.time() - t0, rc, timed_out


def collect(ws, run):
    """Save the agent's diff, report and changed files (agent sees none of the run dir)."""
    subprocess.run(["git", "-C", str(ws), "-c", "core.autocrlf=false", "add", "-A"], check=False)
    diff = subprocess.run(["git", "-C", str(ws), "diff", "--cached", "HEAD"], capture_output=True)
    (run / "agent.diff").write_bytes(diff.stdout)
    names = subprocess.run(["git", "-C", str(ws), "diff", "--cached", "--name-only", "HEAD"],
                           capture_output=True, text=True).stdout.split()
    dst = run / "agent_files"
    for n in names:
        src = ws / n
        if src.is_file() and src.stat().st_size < 2_000_000:
            (dst / n).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / n)
    rep = ws / "AGENT_REPORT.md"
    if rep.exists():
        shutil.copy2(rep, run / "AGENT_REPORT.md")
    # Vivado time spent by the agent's own tool calls
    viv = 0
    for j in list(ws.rglob("synth.json")) + list(ws.rglob("impl.json")):
        try:
            viv += int(json.loads(j.read_text()).get("vivado_seconds") or 0)
        except (ValueError, OSError):
            pass
    return names, viv


def find_one(ws, name, preferred, module=None):
    """Expected path first, then the file name anywhere, then (for Verilog) any
    file that defines `module` (agents sometimes pick their own file name)."""
    if (ws / preferred).exists():
        return ws / preferred
    skip = {"tasks", "tools", ".git", "sim_logs", "equiv_logs"}
    hits = [p for p in ws.rglob(name) if not skip & set(p.parts)]
    if hits or not module:
        return hits[0] if hits else None
    pat = re.compile(rf"^\s*module\s+{module}\b", re.M)
    for p in sorted(ws.rglob("*.v")):
        if not skip & set(p.parts) and pat.search(p.read_text(errors="ignore")):
            return p
    return None


def judge(track, ws, run, assist):
    t0 = time.time()
    extra = ["--assist"] if assist else []
    if track == "H":
        cand = find_one(ws, "red_pitaya_notch_block.v", RTL_REL / "red_pitaya_notch_block.v",
                        module="red_pitaya_notch_block")
        if cand is None:
            (run / "judge.json").write_text(json.dumps(dict(track="H", assist=assist, status="NO_CANDIDATE",
                                            error="agent produced no red_pitaya_notch_block.v", cases=[], checks={})))
            log("judge H: NO_CANDIDATE")
            return time.time() - t0, None
        cmd = [PY, str(HARNESS / "judge" / "notch" / "run_judge.py"), str(run), str(cand)] + extra
    elif track == "B":
        cand = [ws / RTL_REL / f for f in ("red_pitaya_pid_block.v", "red_pitaya_filter_block.v",
                                           "red_pitaya_lpf_block.v")]
        cmd = [PY, str(HARNESS / "judge" / "pid_equiv" / "run_judge.py"), str(run)] + [str(c) for c in cand] + extra
    else:
        bj = ws / "bugs.json"
        cand = bj if bj.exists() else find_one(ws, "bugs.json", "bugs.json") or bj
        cmd = [PY, str(HARNESS / "judge" / "bughunt" / "score.py"), str(run), str(cand)] + extra
    r = subprocess.run(cmd, capture_output=True, text=True)
    (run / "judge_console.log").write_text(r.stdout + r.stderr)
    if not (run / "judge.json").exists():   # judge crashed: record why instead of leaving no result
        (run / "judge.json").write_text(json.dumps(dict(
            track=track, assist=assist, status="JUDGE_ERROR", candidate=str(cand),
            error=(r.stderr or r.stdout).strip()[-1500:] or f"judge exited with code {r.returncode}",
            cases=[], checks={})))
        log(f"JUDGE {track}: JUDGE_ERROR (see judge_console.log)")
        return time.time() - t0, cand
    log((r.stdout.strip().splitlines() or ["judge produced no output"])[0])
    return time.time() - t0, cand


def qor(track, cand, run):
    """Synthesis / implementation of the agent's design with a clean copy of the tools."""
    if track not in ("H", "B") or cand is None:
        return 0
    tools = run / "judge_tools"
    if tools.exists():
        shutil.rmtree(tools)
    shutil.copytree(HARNESS / "tools", tools)
    sh = shutil.which("bash") or "bash"
    subprocess.run([sh, "-c", f'source "{(HARNESS / "lib" / "common.sh").as_posix()}" && '
                              f'write_tool_env "{tools.as_posix()}/tool_env.sh"'], check=True)
    work = run / "qor"; work.mkdir(exist_ok=True)
    if track == "H":
        cmd = [sh, (tools / "run_synth.sh").as_posix(), "red_pitaya_notch_block", Path(cand).as_posix()]
        out = "synth.json"
    else:
        shutil.copy2(HARNESS / "tasks" / "B" / "baseline.json", run / "baseline.json")
        period = json.loads((run / "baseline.json").read_text())["T_target_ns"]
        cmd = [sh, (tools / "run_impl.sh").as_posix(), "red_pitaya_pid_block", str(period)] + \
              [Path(c).as_posix() for c in cand]
        out = "impl.json"
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    (run / "qor_console.log").write_text(r.stdout + r.stderr)
    if (work / out).exists():
        shutil.copy2(work / out, run / out)
        log(r.stdout.strip().splitlines()[0] if r.stdout.strip() else f"{out} written")
        try:
            return int(json.loads((work / out).read_text()).get("vivado_seconds") or 0)
        except ValueError:
            return 0
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run"); ap.add_argument("ws"); ap.add_argument("track")
    ap.add_argument("--assist", action="store_true"); ap.add_argument("--interactive", action="store_true")
    a = ap.parse_args()
    run, ws = Path(a.run).resolve(), Path(a.ws).resolve()
    meta_p = run / "run_meta.json"
    meta = json.loads(meta_p.read_text())
    t_all = time.time()

    check_upstream()
    proxy = start_proxy(run)
    log(f"proxy up on :{ENV['proxy_port']} -> {ENV['upstream_url']}; agent model {ENV['model']}")
    try:
        agent_s, rc, timed_out = run_agent(ws, a.track, a.interactive, run)
    finally:
        proxy.terminate()
        try:
            proxy.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proxy.kill()
    log(f"agent finished: rc={rc} timed_out={timed_out} after {agent_s / 60:.1f} min")

    changed, viv_agent = collect(ws, run)
    log(f"agent changed {len(changed)} files")
    judge_s, cand = judge(a.track, ws, run, a.assist)
    viv_judge = qor(a.track, cand, run)

    leak = subprocess.run([PY, str(HARNESS / "judge" / "leak_check.py"), str(run), str(ws)],
                          capture_output=True, text=True)
    (run / "leak_check.json").write_text(leak.stdout)
    if leak.returncode:
        log("LEAK SUSPECTED: hidden material reached the agent; run marked invalid")

    sys.path.insert(0, str(HARNESS / "report"))
    import metrics as M
    met = M.compute(run)
    meta.update(wall_seconds=round(agent_s, 1), agent_rc=rc, agent_timed_out=timed_out,
                judge_seconds=round(judge_s, 1), llm_seconds=met["llm_seconds"],
                vivado_seconds=viv_agent + viv_judge, files_changed=len(changed),
                total_seconds=round(time.time() - t_all, 1))
    meta_p.write_text(json.dumps(meta, indent=1))
    rep = subprocess.run([PY, str(HARNESS / "report" / "make_report.py"), str(run)], capture_output=True, text=True)
    log(rep.stdout.strip() or rep.stderr.strip()[-500:])
    subprocess.run([PY, str(HARNESS / "report" / "make_report.py"), "--summary"], capture_output=True)
    log(f"done: {run / 'report.html'}  (summary: {ROOT / 'runs' / 'summary.html'})")


if __name__ == "__main__":
    main()
