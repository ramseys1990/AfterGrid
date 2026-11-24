import sqlite3
import pytest
from core.content_backup_guard import guard,content_admission

def test_content_maintenance_admission(tmp_path):
    with sqlite3.connect(tmp_path/"downloads.sqlite3") as db:
        db.execute("CREATE TABLE downloads(state TEXT)")
        db.execute("INSERT INTO downloads VALUES('queued')")
    with pytest.raises(ValueError):guard(tmp_path,"begin",1)
    with sqlite3.connect(tmp_path/"downloads.sqlite3") as db:db.execute("UPDATE downloads SET state='complete'")
    (tmp_path/"map-job.json").write_text('{"state":"downloading"}')
    with pytest.raises(ValueError):guard(tmp_path,"begin",1)
    (tmp_path/"map-job.json").write_text('{"state":"complete"}')
    guard(tmp_path,"begin",1)
    with pytest.raises(ValueError):
        with content_admission(tmp_path):pass
    with pytest.raises(ValueError):guard(tmp_path,"end",2)
    guard(tmp_path,"end",1)
    with content_admission(tmp_path):pass
