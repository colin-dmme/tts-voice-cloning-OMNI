import sqlite3, json
from pathlib import Path
db=sqlite3.connect(r"C:\Coder\tts-voice-cloning-OMNI\config\mcp_jobs.sqlite3")
db.row_factory=sqlite3.Row
row=db.execute("select * from mcp_jobs where job_id=?",("f5b4b79f76124d51be4701aaee0be805",)).fetchone()
data=dict(row) if row else None
if data and data.get("request_json"):
    data["request"]=json.loads(data.pop("request_json"))
if data and data.get("result_json"):
    data["result"]=json.loads(data.pop("result_json"))
print(json.dumps(data,ensure_ascii=False))
