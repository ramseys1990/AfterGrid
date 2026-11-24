import json
import pytest
import recover

def test_inventory_rejects_unverified_core_and_duplicate(tmp_path):
    inventory=tmp_path/"inventory.json"
    rows=[{"key":"core","source":recover.CORE_SOURCE,"snapshot_id":"a"*32,"snapshot_job":1,"verification":"isolated","repository_status":"present"},
          {"key":"worker","source":recover.WORKER_SOURCE,"snapshot_id":"b"*32,"snapshot_job":2,"verification":"isolated","repository_status":"present","envelope_sha256":"c"*64}]
    def save():inventory.write_text(json.dumps({"format":1,"atomic":False,"records":rows}))
    save()
    assert recover.core_records(inventory)["worker"]["snapshot_job"]==2
    rows[0]["verification"]="not recorded"
    save()
    with pytest.raises(ValueError):recover.core_records(inventory)
    rows[0]["verification"]="isolated"
    rows.append(rows[0])
    save()
    with pytest.raises(ValueError):recover.core_records(inventory)
