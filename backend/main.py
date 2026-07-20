from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import db
from agent import run_agent

app = FastAPI(title="Aspri Engine API")

# Setup CORS security rules so Next.js can communicate with FastAPI safely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    user_id: str
    prompt: str
    history: List[dict] = []

class TaskFilterRequest(BaseModel):
    user_id: str
    filter_type: str = "open"

@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest):
    try:
        reply, changed = run_agent(payload.user_id, payload.history, payload.prompt)
        return {"reply": reply, "changed": changed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks")
async def get_tasks(payload: TaskFilterRequest):
    try:
        tasks = db.list_todos(payload.user_id, filter=payload.filter_type)
        return {"tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks/complete/{todo_id}")
async def complete_task(todo_id: str):
    try:
        updated_task = db.complete_todo(todo_id)
        return {"success": True, "task": updated_task}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
