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
  case "$1 ${2:-}" in
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


def test_pending_install_requires_unchanged_config_and_setup_token(tmp_path):
    import hashlib
    import shlex
    root=tmp_path
    (root/"data/core").mkdir(parents=True)
    token=root/"data/core/setup-token"
    token.write_text("a"*64+"\n")
    token.chmod(0o600)
    for name in (".env","compose.yaml"):
        (root/name).write_text("fixture\n")
    marker=root/".install-pending"
    marker.write_text("".join(hashlib.sha256((root/name).read_bytes()).hexdigest()+"  "+name+"\n" for name in (".env","compose.yaml")))
    marker.chmod(0o600)
    cmd="validate_pending_install "+shlex.quote(str(root))
    result=run(cmd)
    assert result.returncode==0,result.stderr
    (root/".env").write_text("changed\n")
    assert run(cmd).returncode!=0
    (root/".env").write_text("fixture\n")
    token.unlink()
    assert run(cmd).returncode!=0
    token.write_text("a"*64+"\n")
    token.chmod(0o600)
    marker.unlink()
    assert run(cmd).returncode!=0


# Model supported Docker commands, including an unlabeled running workload.
# Unsupported filters and attempted mutations fail rather than being mocked away.
RESUME_DOCKER = r'''
docker(){
  case "$1 ${2:-}" in
    "ps -a") printf '%s\n' "$RESUME_ROWS" ;;
    "ps --format") printf '%s\n' "$RUNNING_ROWS" ;;
    *) echo "Unsupported Docker command or mutation" >&2; return 1 ;;
  esac
}
ss(){ printf '%s\n' "$SS_LISTENERS"; }
'''

CORE_ROW="core-id|aftergrid-core|core|/opt/aftergrid|/opt/aftergrid/compose.yaml"
WORKER_ROW="worker-id|aftergrid-core|worker|/opt/aftergrid|/opt/aftergrid/compose.yaml"

def resume_with(rows, running="", listeners=""):
    import shlex
    settings="\n".join(name+"="+shlex.quote(value) for name,value in (
        ("RESUME_ROWS",rows),("RUNNING_ROWS",running),("SS_LISTENERS",listeners)))
    return run(RESUME_DOCKER+"\n"+settings+"\nresume_resources /opt/aftergrid 8080")

def test_resume_uses_supported_docker_listing_and_excludes_own_core_port():
    result=resume_with(CORE_ROW+"\n"+WORKER_ROW,
        "aftergrid-core|192.168.4.73:8080->8080/tcp\nother|0.0.0.0:18080->80/tcp",
        listeners="owned core listener")
    assert result.returncode==0,result.stderr

def test_resume_refuses_labeled_and_unlabeled_foreign_port_conflicts():
    for project in ("other",""):
        result=resume_with(CORE_ROW,
            "aftergrid-core|192.168.4.73:8080->8080/tcp\n"
            +project+"|0.0.0.0:8080->80/tcp")
        assert result.returncode!=0
        assert "Another Docker workload publishes portal port 8080" in result.stderr

def test_resume_without_core_checks_native_listener():
    assert resume_with(WORKER_ROW).returncode==0
    result=resume_with(WORKER_ROW,listeners="foreign host listener")
    assert result.returncode!=0 and "already has a listener" in result.stderr

def test_resume_refuses_unexpected_aftergrid_resources():
    for row in (
        "id|aftergrid-homebox|homebox|/opt/aftergrid/modules/homebox|/opt/aftergrid/modules/homebox/compose.yaml",
        CORE_ROW.replace("/opt/aftergrid|","/another/root|"),
        CORE_ROW.replace("core-id|aftergrid-core|core|","id|aftergrid-core|unexpected|"),
        CORE_ROW.replace("/opt/aftergrid/compose.yaml","/another/compose.yaml"),
    ):
        result=resume_with(row)
        assert result.returncode!=0 and "Unexpected AfterGrid container" in result.stderr

def test_resume_fails_closed_when_docker_inspection_fails():
    inventory_failure=run("docker(){ return 1; }; resume_resources /opt/aftergrid 8080")
    assert inventory_failure.returncode!=0
    assert "Cannot inspect containers" in inventory_failure.stderr
    ports_failure=run(
        'docker(){ if [[ "$2" == -a ]]; then :; else return 1; fi; }; '
        'resume_resources /opt/aftergrid 8080')
    assert ports_failure.returncode!=0
    assert "Cannot inspect Docker ports" in ports_failure.stderr
