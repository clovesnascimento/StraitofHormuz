# -*- coding: utf-8 -*-
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  ⚓  Agente Hormuz                                                           
# │  Criador    : Cloves Nascimento                                                  
# │  Papel      : Arquiteto de Ecossistemas Cognitivos                                                     
# │  Org        : CNGSM - Cognitive Neural & Generative Systems Management                                                      
# │  Versão     : 1.0.0                                                  
# │  Fingerprint: 8a3ee43b0c78e2b4                                              
# │  SHA-256    : 8a3ee43b0c78e2b4cb77204ffc5fb4ed6a33d8f90af59435d19533d9739c7d00                                                   
# │                                                                          
# │  © 2025 Cloves Nascimento — Todos os direitos reservados.                     
# │  Distribuição e modificação sujeitas aos termos da licença CNGSM.       
# └─────────────────────────────────────────────────────────────────────────┘

"""
CNGSM — Agente Hormuz
Daemon: instala e gerencia o agente como serviço de background
Suporta: Windows (NSSM/Task Scheduler) e Linux (systemd)
"""

import os
import platform
import signal
import subprocess
import sys
from pathlib import Path

HORMUZ_HOME = Path.home() / ".hormuz"
PID_FILE    = HORMUZ_HOME / "hormuz.pid"
PYTHON      = sys.executable
AGENT_SCRIPT = Path(__file__).parent.parent / "ui" / "cli.py"

# ─────────────────────────────────────────────────────────────
# PID management
# ─────────────────────────────────────────────────────────────

def _read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None

def _is_running(pid: int) -> bool:
    if platform.system() != "Windows":
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
    
    # Windows fix: use psutil or tasklist
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        # fallback to tasklist
        try:
            res = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=2
            )
            return str(pid) in res.stdout
        except Exception:
            return False

def status():
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"[Hormuz] RUNNING — PID {pid}")
    else:
        print("[Hormuz] STOPPED")

def stop():
    pid = _read_pid()
    if not pid or not _is_running(pid):
        print("[Hormuz] Not running.")
        return
    os.kill(pid, signal.SIGTERM)
    print(f"[Hormuz] Sent SIGTERM to PID {pid}")

# ─────────────────────────────────────────────────────────────
# Linux systemd service
# ─────────────────────────────────────────────────────────────

SYSTEMD_UNIT = """\
[Unit]
Description=CNGSM Agente Hormuz
After=network.target

[Service]
Type=simple
ExecStart={python} {script} {sandbox}
Restart=on-failure
RestartSec=5
Environment=HORMUZ_HOME={hormuz_home}
StandardOutput=append:{log}
StandardError=append:{log}

[Install]
WantedBy=default.target
"""

def install_systemd(sandbox: str):
    unit_dir  = Path.home() / ".config" / "systemd" / "user"
    unit_file = unit_dir / "hormuz.service"
    unit_dir.mkdir(parents=True, exist_ok=True)
    content = SYSTEMD_UNIT.format(
        python      = PYTHON,
        script      = AGENT_SCRIPT,
        sandbox     = sandbox,
        hormuz_home = HORMUZ_HOME,
        log         = HORMUZ_HOME / "hormuz.log",
    )
    unit_file.write_text(content)
    subprocess.run(["systemctl", "--user", "daemon-reload"])
    subprocess.run(["systemctl", "--user", "enable", "hormuz"])
    subprocess.run(["systemctl", "--user", "start",  "hormuz"])
    print(f"[Hormuz] Installed as systemd user service: {unit_file}")
    print("[Hormuz] Status: systemctl --user status hormuz")

# ─────────────────────────────────────────────────────────────
# Windows Task Scheduler
# ─────────────────────────────────────────────────────────────

TASK_XML = """\
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions>
    <Exec>
      <Command>{python}</Command>
      <Arguments>"{script}" "{sandbox}"</Arguments>
      <WorkingDirectory>{workdir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""

def install_windows(sandbox: str):
    HORMUZ_HOME.mkdir(parents=True, exist_ok=True)   # ensure home dir exists
    xml_path = HORMUZ_HOME / "hormuz_task.xml"
    xml_content = TASK_XML.format(
        python  = PYTHON,
        script  = AGENT_SCRIPT,
        sandbox = sandbox,
        workdir = HORMUZ_HOME,
    )
    xml_path.write_text(xml_content, encoding="utf-16")
    result = subprocess.run(
        ["schtasks", "/Create", "/TN", "HormuzAgent", "/XML", str(xml_path), "/F"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("[Hormuz] Installed in Windows Task Scheduler.")
        print("[Hormuz] Starts automatically on logon.")
        print("[Hormuz] Manage: Task Scheduler → HormuzAgent")
    else:
        print(f"[Hormuz] Install failed: {result.stderr}")

# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python daemon.py [install|start|stop|status] [sandbox_path]")
        sys.exit(1)

    cmd     = sys.argv[1].lower()
    sandbox = sys.argv[2] if len(sys.argv) > 2 else str(Path.cwd())

    if cmd == "status":
        status()
    elif cmd == "stop":
        stop()
    elif cmd in ("install", "start"):
        if platform.system() == "Linux":
            install_systemd(sandbox)
        elif platform.system() == "Windows":
            install_windows(sandbox)
        else:
            # macOS or other — run directly in background
            proc = subprocess.Popen(
                [PYTHON, str(AGENT_SCRIPT), sandbox],
                stdout=open(HORMUZ_HOME / "hormuz.log", "a"),
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
            PID_FILE.write_text(str(proc.pid))
            print(f"[Hormuz] Started in background — PID {proc.pid}")
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
