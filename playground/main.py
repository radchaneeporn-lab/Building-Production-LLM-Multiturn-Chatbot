# this file just for learn FastAPI
# run this file with this command `uvicorn main:app --reload`
# `http:127.0.0.1:8000/docs`
# import fastapi
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
# create app instance
app = FastAPI()

# import BaseModel from Pydantic, then define a class called Task
class Task(BaseModel):
	id: int
	title: str
	done: bool = False # true/ false, defaults False
	
tasks = []


# add a route, the decorator @app.get tell fastAPI when someone visits the homepage, run this function
@app.get("/")
def read_root():
	return {"message":"My API is live!"}
	
# this @app.post reads and validates the JSON body, this function takes a task argument, typed as Task, FastAPI parses the json body, checks the types, and hands you  a real Python object, append it to a list, and return it, don't need to wrote a single line of validation
 
@app.post("/task")
def create_task(task: Task):
	tasks.append(task)
	return task
	
@app.get("/tasks/{task_id}")
def get_task(task_id: int):
	for task in tasks:
		if task.id == task_id:
			return task
	raise HTTPException(404, "Task not found")
	
@app.delete("tasks/{task_id}")
def delete_task(task_id: int):
	for i,task in enumerate(tasks):
		if task.id == task_id:
			tasks.pop(i)
			return {"deleted": task_id}
	raise HTTPException(404, "Task not found")	