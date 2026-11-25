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
