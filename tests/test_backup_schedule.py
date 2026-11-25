import pytest
from core.backup_schedule import BackupSchedules,INTERVALS

def test_schedule_due_once_and_no_catchup(tmp_path):
    now=[100]
    schedule=BackupSchedules(tmp_path,lambda:now[0])
    schedule.configure("core",True,"daily")
    calls=[]
    jobs=[]
    def call(path,payload=None):
        calls.append((path,payload))
        if path=="/jobs" and payload is None:return 200,jobs
        if path.startswith("/backup-policy/"):return 200,{"policy":{"schedule":{"automatic_policy":False}}}
        if payload=={"module":"kopia","action":"core-snapshot"}:
            jobs.append({"id":1,"module":"kopia","action":"core-snapshot","state":"queued"})
            return 202,{"id":1}
        assert payload=={"module":"kopia","action":"core-verify-snapshot","source_job":1}
        jobs.append({"id":2,"module":"kopia","action":"core-verify-snapshot","state":"queued"})
        return 202,{"id":2}
    schedule.tick(call,lambda:None)
    assert not any(p for _,p in calls)
    now[0]+=INTERVALS["daily"]*4
    schedule.tick(call,lambda:None)
    assert schedule.load()["core"]["next_due"]==now[0]+INTERVALS["daily"]
    schedule.tick(call,lambda:None)
    assert len([p for _,p in calls if p])==1
    jobs[0]["state"]="succeeded"
    schedule.tick(call,lambda:None)
    row=schedule.load()["core"]
    assert row["source_job"]==1 and row["verification"]=="queued" and row["job"]==2
    jobs[1]["state"]="succeeded"
    schedule.tick(call,lambda:None)
    assert schedule.load()["core"]["verification"]=="succeeded"
    assert len([p for _,p in calls if p])==2


def test_failed_or_uncertain_dispatch_pauses_schedule(tmp_path):
    now=[100]
    schedule=BackupSchedules(tmp_path,lambda:now[0])
    schedule.configure("application/grocy",True,"weekly")
    now[0]+=INTERVALS["weekly"]
    def call(path,payload=None):
        if path=="/jobs" and payload is None:return 200,[]
        if path.startswith("/backup-policy/"):return 200,{"policy":{"schedule":{"automatic_policy":False}}}
        raise OSError("lost worker response")
    schedule.tick(call,lambda:None)
    assert schedule.load()["application/grocy"]["result"]=="unknown"
    assert not schedule.load()["application/grocy"]["enabled"]
    schedule.configure("application/grocy",True,"weekly")
    rows=schedule.load()
    rows["application/grocy"]["result"]="dispatching"
    schedule.save(rows)
    schedule.tick(lambda *a:pytest.fail("Uncertain slot must not retry"),lambda:None)
    assert not schedule.load()["application/grocy"]["enabled"]


def test_busy_and_native_automatic_policy_defer(tmp_path):
    now=[100]
    schedule=BackupSchedules(tmp_path,lambda:now[0])
    schedule.configure("worker",True,"daily")
    now[0]+=INTERVALS["daily"]
    def call(path,payload=None):
        if path=="/jobs" and payload is None:return 200,[]
        if path.startswith("/backup-policy/"):return 200,{"policy":{"schedule":{"automatic_policy":True}}}
        pytest.fail("Must not dispatch")
    schedule.tick(call,lambda:None)
    assert schedule.load()["worker"]["result"]=="not run"
    with pytest.raises(RuntimeError):schedule.tick(call,lambda:(_ for _ in ()).throw(RuntimeError("busy")))
    assert schedule.load()["worker"]["enabled"]
    with pytest.raises(ValueError):schedule.configure("application/tak",True,"daily")


def test_failed_job_disables_schedule(tmp_path):
    schedule=BackupSchedules(tmp_path,lambda:100)
    schedule.configure("core",True,"daily")
    rows=schedule.load()
    rows["core"].update(job=7,result="queued")
    schedule.save(rows)
    schedule.tick(lambda path:(200,[{"id":7,"module":"kopia","action":"core-snapshot","state":"failed"}]),lambda:None)
    assert schedule.load()["core"]["result"]=="failed" and not schedule.load()["core"]["enabled"]


def test_verification_failure_pauses_and_never_claims_verified(tmp_path):
    schedule=BackupSchedules(tmp_path,lambda:100)
    schedule.configure("core",True,"daily")
    rows=schedule.load()
    rows["core"].update(phase="verify",source_job=7,job=8,result="queued",verification="queued")
    schedule.save(rows)
    schedule.tick(lambda path:(200,[{"id":8,"module":"kopia","action":"core-verify-snapshot","state":"failed"}]),lambda:None)
    row=schedule.load()["core"]
    assert row["verification"]=="failed" and not row["enabled"] and row["source_job"]==7
