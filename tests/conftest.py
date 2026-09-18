import pytest
from fastapi.testclient import TestClient
from backend.main import create_app

TOKEN='test-operator-token-at-least-16'

@pytest.fixture
def client(tmp_path):
    app=create_app(f'sqlite:///{tmp_path / "test.db"}',admin_token=TOKEN)
    with TestClient(app) as c:
        c.headers['Authorization']='Bearer '+TOKEN
        yield c

def registered(client,device='TEST-SIM',mode='SIMULATION'):
    r=client.post('/api/devices',json={'device_id':device,'name':'Test unit','mode':mode})
    assert r.status_code==201,r.text
    return r.json()['device_token']
