import os
import time
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from passlib.hash import bcrypt
from pymongo.mongo_client import MongoClient
import openai

app = FastAPI()
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# MongoDB configuration
MONGO_DB = os.getenv("MONGO_DB")
MONGODB_URL = MONGO_DB
mongo_client = MongoClient(MONGODB_URL)
db = mongo_client["safeplan"]
users_collection = db["users"]


# Define the User model
class User:
    def __init__(self, username: str, created_at: datetime):
        self.username = username
        self.created_at = created_at


# Dependency to get the MongoDB database connection
def get_db():
    try:
        yield db
    finally:
        pass


# Endpoint to generate responses
@app.post("/generate-response")
async def generate_response(request: Request):
    try:
        data = await request.json()
        user_message = data["user_message"]

        # Create an OpenAI assistant
        assistant = openai.OpenAI().beta.assistants.create(
            name="Travel Planner",
            instructions="You help planning travel itineraries, skilled in choosing places to stay,"
                         " restaurants, tourist sites, and more.",
            model="gpt-3.5-turbo",  # gpt-4-1106-preview
        )

        # Create a thread for communication
        thread = openai.OpenAI().beta.threads.create()

        # Send user message
        message = openai.OpenAI().beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_message,
        )

        # Start the assistant
        run = openai.OpenAI().beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id,
            instructions="Please address the user's travel inquiries.",
        )

        # Wait for completion
        while True:
            run = openai.OpenAI().beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

            if run.status == "completed":
                messages = openai.OpenAI().beta.threads.messages.list(thread_id=thread.id)

                response = ""
                for message in messages:
                    if message.role == "assistant" and message.content[0].type == "text":
                        response += message.content[0].text.value + "\n"

                # Delete assistant
                openai.OpenAI().beta.assistants.delete(assistant.id)

                return JSONResponse(content={"response": response}, status_code=200)

            else:
                time.sleep(5)

    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))


# New API endpoint to check if username and password are valid
@app.post("/check-credentials")
async def check_credentials(request: Request, db=Depends(get_db)):
    try:
        data = await request.json()
        username = data["username"]
        password = data["password"]

        # Retrieve user from MongoDB based on username
        users_data = db.users.find({"username": username})

        if users_data:
            for user in users_data:
                # Get the stored password hash from the user data
                stored_password_hash = user.get("password")
                if stored_password_hash:
                    # Verify the provided password with the stored password hash
                    if bcrypt.verify(password, stored_password_hash):
                        return JSONResponse(content={"message": "Credentials are valid"}, status_code=200)
                    else:
                        raise HTTPException(status_code=401, detail="Invalid credentials")
                else:
                    raise HTTPException(status_code=401, detail="No password hash found for the user")
        else:
            raise HTTPException(status_code=401, detail="User not found")

    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))


# New API endpoint to add a new user to the database
@app.post("/add-user")
async def add_user(request: Request, db=Depends(get_db)):
    try:
        data = await request.json()
        username = data["username"]
        password = data["password"]  # Assuming plaintext password for now

        # Check if the username already exists in the database
        existing_users = db.users.find({"username": username})
        for user in existing_users:
            if user:
                raise HTTPException(status_code=400, detail="Username already exists")

        # Hash the password using bcrypt (for security)
        hashed_password = bcrypt.hash(password)

        # Create a new user object
        new_user = {"username": username, "password": hashed_password, "created_at": datetime.utcnow()}

        # Insert the new user into the database
        db.users.insert_one(new_user)

        return JSONResponse(content={"message": "User added successfully"}, status_code=201)

    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))


@app.put("/update-user/{username}")
async def update_user(username: str, request: Request):
    try:
        # Parse request JSON data
        data = await request.json()

        # Update user information in the database
        result = db.users.update_one({"username": username}, {"$set": data})

        if result.modified_count == 1:
            return {"message": "User updated successfully"}
        else:
            raise HTTPException(status_code=404, detail="User not found")

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get-user/{username}")
async def get_user(username: str):
    try:
        # Query the database to find the user by username
        users = users_collection.find({"username": username})

        # If user is found, return user data as JSON
        if users:
            for user in users:
                user["_id"] = str(user["_id"])
                user = convert_to_json_serializable(user)
                return JSONResponse(content=user, status_code=200)
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def convert_to_json_serializable(user):
    """Converts datetime objects to ISO 8601 formatted strings."""
    for key, value in user.items():
        if isinstance(value, datetime):
            user[key] = value.isoformat()
    return user


@app.get("/test-api")
async def test_api():
    try:
        return 'hello'
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/test-connection")
async def test_connection():
    try:
        # Connect to MongoDB
        # client = MongoClient(MONGO_DB)
        # db = mongo_client.get_default_database()
        return MONGO_DB
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Run the FastAPI application with Uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0")
    # uvicorn.run(app, host="192.168.56.1", port=8000)
