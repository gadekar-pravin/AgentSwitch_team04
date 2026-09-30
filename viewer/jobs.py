"""One harness run at a time, started through the same CLI a person would type."""
import datetime as dt
import subprocess
import sys
import threading
from pathlib import Path

from prod_agent import config


class JobError(Exception):
    pass


class JobRunner:
    def __init__(self, tasks: list[dict], demo_base: Path, popen=subprocess.Popen):
        self.tasks = {t["id"]: t for t in tasks}
        self.demo_base = demo_base
        self._popen = popen
        self._lock = threading.Lock()
        self._next_id = 0
        self.current: dict | None = None

    def instances_for(self, task_id: str) -> list[str]:
        return self.tasks[task_id].get("instances", sorted(config.INSTANCES))

    def start(self, task_id: str, instance: str, confirm: str) -> dict:
        if task_id not in self.tasks:
            raise JobError(f"unknown task {task_id!r}")
        if instance not in self.instances_for(task_id):
            raise JobError(f"task {task_id} does not run on {instance!r}")
        if confirm != f"{instance}/{task_id}":
            raise JobError("confirmation text does not match")
        with self._lock:
            # Two runs share the fixture work orders on the tenant and would trip changed_underneath on each other.
            if self.current is not None and self.current["proc"].poll() is None:
                raise JobError("a run is already in progress")
            self.demo_base.mkdir(parents=True, exist_ok=True)
            before = {p.name for p in self.demo_base.iterdir()}
            started = dt.datetime.now()
            log_path = self.demo_base / f"console-{started:%Y%m%d-%H%M%S}.log"
            # An argument list, never a shell string: task and instance only ever come from the allowlist above.
            cmd = [sys.executable, "-m", "harness.runner", "--task", task_id, "--instance", instance,
                   "--runs-dir", str(self.demo_base)]
            with log_path.open("w", encoding="utf-8") as log:
                # A new session keeps Ctrl-C on the console from killing the run before it withdraws its escalations.
                proc = self._popen(cmd, cwd=config.ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
            self._next_id += 1
            self.current = {"job_id": self._next_id, "task_id": task_id, "instance": instance, "proc": proc,
                            "before": before,
                            "log": str(log_path), "started": started.isoformat(timespec="seconds")}
        return self.status()

    def status(self) -> dict | None:
        if self.current is None:
            return None
        cur = self.current
        new = sorted(p.name for p in self.demo_base.iterdir() if p.is_dir() and p.name not in cur["before"])
        code = cur["proc"].poll()
        return {"job_id": cur["job_id"], "task_id": cur["task_id"], "instance": cur["instance"],
                "started": cur["started"],
                "running": code is None, "exit_code": code, "run_root": new[-1] if new else None,
                "log": cur["log"]}
