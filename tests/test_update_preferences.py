import datetime as dt
import pytest
from core.update_preferences import UpdatePreferences


def test_weekly_utc_window_and_private_persistence(tmp_path):
    clock=[dt.datetime(2026,11,23,1,59,tzinfo=dt.timezone.utc).timestamp()]
    prefs=UpdatePreferences(tmp_path,lambda:clock[0])
    assert prefs.report("kiwix")["preference"] is None
    row={"enabled":True,"weekday":0,"start_minute":120,"duration_minutes":120}
    result=prefs.configure("kiwix",row)
    assert result["next_window_start"]==clock[0]+60
    assert not result["execution_enabled"] and result["activation_required"]
    assert prefs.path.stat().st_mode&0o777==0o600
    clock[0]+=60
    assert prefs.report("kiwix")["window_open"]
    assert prefs.report("kiwix")["current_window_end"]==clock[0]+7200
    clock[0]+=7200
    assert not prefs.report("kiwix")["window_open"]
    assert prefs.report("kiwix")["next_window_start"]==clock[0]+7*86400-7200
    assert UpdatePreferences(tmp_path).load()["kiwix"]==row
    assert not prefs.configure("kiwix",{**row,"enabled":False})["window_open"]
    with pytest.raises(ValueError):prefs.configure("grocy",row)
    with pytest.raises(ValueError):prefs.configure("kiwix",{**row,"start_minute":1430})
    with pytest.raises(ValueError):prefs.configure("kiwix",{**row,"weekday":True})
    prefs.path.chmod(0o644)
    with pytest.raises(ValueError):prefs.load()


def test_update_scheduler_release_activation_and_single_claim(tmp_path,monkeypatch):
    from core import update_preferences as module
    clock=[dt.datetime(2026,11,23,2,1,tzinfo=dt.timezone.utc).timestamp()]
    prefs=UpdatePreferences(tmp_path,lambda:clock[0])
    row={"enabled":True,"weekday":0,"start_minute":120,"duration_minutes":120}
    prefs.configure("kiwix",row)
    calls=[]
    image="sha256:"+"a"*64
    target="sha256:"+"b"*64
    candidate="ghcr.io/kiwix/kiwix-serve:3.8.2@sha256:"+"c"*64
    local={"status":"registry check required","candidate":candidate,"platform":"linux/amd64",
           "installed_image_ids":[image],"expected_target_image_id":target}
    def call(path,payload=None,**kw):
        calls.append((path,payload))
        if path=="/update-eligibility/kiwix":return 200,local
        if path=="/update-eligibility":return 200,{**local,"status":"reviewed candidate confirmed"}
        assert path=="/guarded-update" and payload=={"candidate":candidate,"platform":"linux/amd64",
            "previous_image_id":image,"target_image_id":target}
        return 202,{"id":19}
    with pytest.raises(ValueError):prefs.activate(True)
    prefs.tick(call,lambda:None)
    assert not calls
    monkeypatch.setattr(module,"EXECUTION_ENABLED",True)
    prefs.tick(call,lambda:None)
    assert not calls
    prefs.activate(True)
    prefs.tick(call,lambda:None)
    assert len(calls)==3 and prefs.report("kiwix")["dispatch"]["job"]==19
    UpdatePreferences(tmp_path,lambda:clock[0]).tick(call,lambda:None)
    assert len(calls)==3
    clock[0]+=7*86400
    def lost(path,payload=None,**kw):
        if path=="/guarded-update":raise TimeoutError("ambiguous")
        return call(path,payload,**kw)
    with pytest.raises(TimeoutError):prefs.tick(lost,lambda:None)
    assert prefs.report("kiwix")["dispatch"]["status"]=="uncertain"
    prefs.tick(call,lambda:None)
    assert len(calls)==5
    prefs.configure("kiwix",row)
    assert not prefs.report("kiwix")["execution_enabled"]
    prefs.activate(True)
    prefs.tick(call,lambda:None)
    assert len(calls)==5
