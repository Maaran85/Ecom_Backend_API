from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

@app.get('/{ticket_id}')
def get_id(ticket_id: int):
    return ticket_id

@app.get('/dealer/my-queue')
def get_queue():
    return 'queue'

client = TestClient(app)
print("Status:", client.get('/dealer/my-queue').status_code)
