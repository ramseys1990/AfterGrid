"""Installer checks run with fake read-only system commands; never touch host Docker."""
import os
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def run(script):
    env={k:v for k,v in os.environ.items() if k not in {"DOCKER_HOST","DOCKER_CONTEXT","BASH_ENV"}}
    return subprocess.run(["bash","-c",'source "$1"; '+script,"installer-test",str(ROOT/"install.sh")],
                          env=env,capture_output=True,text=True)

def test_port_preflight():
    assert run('ss(){ :; }; check_port 8080').returncode==0
    result=run('ss(){ echo listener; }; check_port 8080')
    assert result.returncode and "already has a listener" in result.stderr
    assert run('ss(){ return 1; }; check_port 8080').returncode

def test_docker_preflight_no_mutations():
    mock=r'''
docker(){
  case "$1 $2" in
    "context show") echo default ;;
    "context inspect") echo "${ENDPOINT:-unix:///var/run/docker.sock}" ;;
    "info ") : ;;
    "compose version") : ;;
    "ps -a") echo "${PROJECT:-}" ;;
    "network ls") echo "${NETWORK:-}" ;;
    "volume ls") echo "${VOLUME:-}" ;;
    "ps --format") echo "${PORTS:-}" ;;
    *) echo "Unexpected docker mutation" >&2; return 1 ;;
  esac
}
'''
    for state in ["PROJECT=unrelated","PORTS=0.0.0.0:18080-\\>80/tcp","NETWORK=unrelated"]:
        assert run(mock+"\n"+state+"; check_local_docker 8080").returncode==0
    for state in ["PROJECT=aftergrid-core","NETWORK=aftergrid-apps","VOLUME=aftergrid-core_worker_state",
                  "PORTS=0.0.0.0:8080-\\>80/tcp","ENDPOINT=tcp://other:2375","DOCKER_HOST=ssh://other"]:
        assert run(mock+"\n"+state+"; check_local_docker 8080").returncode!=0
