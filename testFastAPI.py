import os
import time
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from passlib.hash import bcrypt
from pymongo.mongo_client import MongoClient
import openai
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# MongoDB configuration
MONGO_DB = os.getenv("MONGO_DB")
MONGODB_URL = MONGO_DB
mongo_client = MongoClient(MONGODB_URL)
db = mongo_client["safeplan"]
users_collection = db["users"]
templates_collection = db["templates"]

user_details = {}


# Define the User model
class User:
    def __init__(self, email: str, created_at: datetime):
        self.email = email
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
        user_message = get_user_details(data)

        # Create an OpenAI assistant
        assistant = openai.OpenAI().beta.assistants.create(
            name="Travel Planner",
            instructions="You help planning travel itineraries, skilled in choosing places to stay,"
                         " restaurants, tourist sites, and more.",
            model="gpt-4-0125-preview",  # gpt-4-1106-preview gpt-3.5-turbo gpt-4-0125-preview
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


# New API endpoint to check if email and password are valid
@app.post("/check-credentials")
async def check_credentials(request: Request, db=Depends(get_db)):
    try:
        data = await request.json()
        email = data["email"]
        password = data["password"]

        # Retrieve user from MongoDB based on email
        user = db.users.find_one({"email": email})

        if user:  # Check if user exists
            # Get the stored password hash from the user data
            stored_password_hash = user.get("password")
            if stored_password_hash:
                # Verify the provided password with the stored password hash
                if bcrypt.verify(password, stored_password_hash):
                    return JSONResponse(content={"message": "Credentials are valid"}, status_code=200)
                else:
                    return HTTPException(status_code=401, detail="Invalid credentials")
            else:
                return HTTPException(status_code=401, detail="No password hash found for the user")
        else:
            return HTTPException(status_code=401, detail="User not found")

    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))


# New API endpoint to add a new user to the database
@app.post("/add-user")
async def add_user(request: Request, db=Depends(get_db)):
    try:
        data = await request.json()
        email = data["email"]
        password = data["password"]  # Assuming plaintext password for now
        full_name = data["fullName"]
        terms = data["terms"]

        # Check if the email already exists in the database
        existing_users = db.users.find({"email": email})
        for user in existing_users:
            if user:
                raise HTTPException(status_code=400, detail="Email already exists")

        # Hash the password using bcrypt (for security)
        hashed_password = bcrypt.hash(password)

        # Create a new user object
        new_user = {"email": email, "password": hashed_password, "fullName": full_name, "terms": terms}

        # Insert the new user into the database
        db.users.insert_one(new_user)

        return JSONResponse(content={"message": "User added successfully"}, status_code=201)

    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))


@app.put("/update-user/{email}")
async def update_user(email: str, request: Request):
    try:
        # Parse request JSON data
        data = await request.json()

        # Update user information in the database
        result = db.users.update_one({"email": email}, {"$set": data})

        if result.modified_count == 1:
            return {"message": "User updated successfully"}
        else:
            raise HTTPException(status_code=404, detail="User not found")

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get-user/{email}")
async def get_user(email: str):
    try:
        # Query the database to find the user by email
        users = users_collection.find({"email": email})

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
        return MONGO_DB
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_user_details(data):
    global user_details
    try:
        if data:
            # Save user details globally
            user_details = {
                'vacationType': data['vacationType'],
                'originCountry': data['originCountry'],
                'destCountry': data['destCountry'],
                'dates': data['dates'],
                'ages': data['ages'],
                'anotherCityChecked': data['anotherCityChecked'],
                'returnCountry': data['returnCountry'],
                'budget': data['budget'],
                'hotel': data['hotel'],
                'starts': data['stars'],
                'parking': data['parking'],
                'beach': data['beach'],
                'restaurants': data['restaurants'],
                'bars': data['bars'],
                'cities': data['cities'],
                'carRentalCompany': data['carRentalCompany'],
                'dietaryPreferences': data['dietaryPreferences'],
                'additionalData': data['additionalData'],
                'adultsAmount': data['adultsAmount'],
                'childrenAmount': data['childrenAmount']
            }

            return get_templates(user_details['vacationType'])

        else:
            raise HTTPException(status_code=404, detail="User Details not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_general_templates():
    try:
        # Fetch the general-template from the database
        temp = templates_collection.find_one({}, {"_id": 0, "general-template": 1})

        # If template is found, return template data as JSON
        if temp:
            return temp['general-template']
        else:
            raise HTTPException(status_code=404, detail="General template not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_json_template():
    try:
        # Fetch the general-template from the database
        temp = templates_collection.find_one({}, {"_id": 0, "json-template": 1})

        # If template is found, return template data as JSON
        if temp:
            return temp['json-template']
        else:
            raise HTTPException(status_code=404, detail="Json template not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_templates(vacation_type: str):
    try:
        templates = templates_collection.find({"vacationType": vacation_type})

        # If template is found, return template data as JSON
        if templates:
            for temp in templates:
                temp["_id"] = str(temp["_id"])
                temp = temp['template']
                return set_data_to_templates(temp)

        else:
            raise HTTPException(status_code=404, detail="Template not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def set_data_to_templates(template: str):
    try:
        if user_details['anotherCityChecked'] and not user_details['returnCountry'] == '':
            template += f"We would like to return from the country {user_details['returnCountry']}. " \
                        f"When the trip will include travel to this country. "
        if not user_details['cities'] == []:
            template += f"In {user_details['destCountry']} we would like to travel in the cities " \
                        f"{user_details['cities']}. "
        if not user_details['adultsAmount'] is None:
            template += f"We are {user_details['adultsAmount']} adults. "
        if not user_details['childrenAmount'] is None:
            template += f"Please includes {user_details['childrenAmount']} children. "
        if not user_details['carRentalCompany'] == '':
            template += f"In addition, notice that {user_details['carRentalCompany']} - for rent a car. "
        if not user_details['dietaryPreferences'] == '':
            template += f"Notice that I have dietary preferences - {user_details['dietaryPreferences']}," \
                        f" so take this figure into account when you suggest me recommended restaurants and dishes. "
        if not user_details['bars'] == '':
            template += f"About bars - {user_details['bars']}. "
        if not user_details['beach'] == '':
            template += f"About beach - {user_details['beach']}. "
        if not user_details['parking'] == '':
            template += f"About parking - {user_details['parking']}. "
        if not user_details['restaurants'] == '':
            template += f"About restaurants - {user_details['restaurants']}. "
        if not user_details['hotel'] == '':
            template += f"About the hotel - {user_details['hotel']}. "
        if not user_details['additionalData'] == []:
            for additional in user_details['additionalData']:
                template += f"In addition, it is important - {additional}. "

        # Replace placeholders with variables
        formatted_trip_details = template.format(ages=user_details['ages'], date1=str(user_details['dates'][0]),
                                                 date2=str(user_details['dates'][1]),
                                                 from_country=user_details['originCountry'],
                                                 to_country=user_details['destCountry'],
                                                 budget1=str(user_details['budget'][0]),
                                                 budget2=str(user_details['budget'][1]),
                                                 stars=str(user_details['stars']))

        general_template = get_general_templates()
        formatted_trip_details += general_template
        formatted_trip_details += "Please display your response as the json: " + get_json_template()
        return formatted_trip_details

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Run the FastAPI application with Uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0")
