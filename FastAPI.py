import os
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from passlib.hash import bcrypt
from pymongo.mongo_client import MongoClient
import openai
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio

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
history_collection = db['history']
additionalData_collection = db['additionalData']
plans_collection = db['plans']

user_details = {}
response_semaphore = asyncio.Semaphore(1)


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


def get_general_template():
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


def get_instructions():
    try:
        # Fetch the instructions from the database
        # instructions_doc = templates_collection.find_one({}, {"_id": 0, "instructions": 1})

        instructions_doc = templates_collection.find_one({"instructions": {"$exists": True}},
                                                         {"_id": 0, "instructions": 1})
        # If instructions are found, return them
        if instructions_doc and 'instructions' in instructions_doc:
            return instructions_doc['instructions']
        else:
            raise HTTPException(status_code=404, detail="Instructions not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def assist_improve_response(user_message, email):
    try:
        gpt_response = openai.chat.completions.create(
            model="gpt-4-turbo",  # Specify the GPT model
            messages=[
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            temperature=1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )

        trip_plan = gpt_response.choices[0].message.content.strip()

        # trip_plan = gpt_response_content.strip()
        db.plans.update_one(
            {"email": email},
            {"$set": {"plan": json.loads(trip_plan)}}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint to generate responses
@app.post("/generate-response")
async def generate_response(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        email = request.query_params.get("email")

        db.plans.update_one(
            {"email": email},
            {"$set": {"plan": []}}
        )

        user_data = get_user_details(data)
        general_template = get_general_template()
        user_message = user_data + "Please improve your answer according to: " + general_template + get_instructions()

        background_tasks.add_task(assist_improve_response, user_message, email)

        return JSONResponse(content={"message": "Response generation initiated. Please check back later."}, status_code=200)

    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))


@app.post("/improve-response")
async def improve_response(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        user_message = str(data['plan']) + "Please improve your answer according to: " + str(data['general_template']) + get_instructions()

        background_tasks.add_task(assist_improve_response, user_message)

        return JSONResponse(content={"message": "Response generation initiated. Please check back later."}, status_code=200)

    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))


@app.get("/get-improved-response/{email}")
async def get_improved_response(email: str):

    try:
        # Query the database to find the user by email
        plans = plans_collection.find({"email": email})

        # If user is found, return user data as JSON
        if plans:
            for plan in plans:
                plan["_id"] = str(plan["_id"])
                plan = plan["plan"]
                if not plan == []:
                    if email == 'global':
                        plan["saveable"] = False
                    else:
                        plan["saveable"] = True
                    return JSONResponse(content=plan, status_code=200)
                else:
                    return JSONResponse(
                        content={"message": "No improved response available yet. Please try again later."},
                        status_code=503)
        else:
            return JSONResponse(content={"message": "No improved response available yet. Please try again later."},
                                     status_code=503)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        db.history.insert_one({"email": email})
        db.plans.insert_one({"email": email, "plan": []})

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


@app.get("/test-connection")
async def test_connection():
    try:
        return MONGO_DB
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/update-user-history/{email}")
async def update_user_history(email: str, request: Request):
    try:
        # Parse request JSON data
        data = await request.json()

        user = db.history.find_one({"email": email})

        if user:
            # If user exists, get the latest index and increment it
            index = user.get("latest_index", 0) + 1
            history_item = {
                "index": index,
                "data": data,
            }

            # Update user information in the database
            result = db.history.update_one(
                {"email": email},
                {"$push": {"history": history_item}, "$set": {"latest_index": index}}
            )

            if result.modified_count == 1:
                return JSONResponse(content={"message": "User history created successfully", "index": index}, status_code=200)
            else:
                raise HTTPException(status_code=500, detail="Failed to update user history")
        else:
            # If user not found, create a new entry with index 1
            index = 1
            history_item = {
                "index": index,  # Start index from 1
                "data": data
            }

            db.history.insert_one({
                "email": email,
                "history": [history_item],
                "latest_index": index
            })

            return JSONResponse(content={"message": "User history created successfully", "index": index}, status_code=200)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# @app.put("/update-user-history/{email}")
# async def update_user_history(email: str, request: Request):
#     try:
#         # Parse request JSON data
#         data = await request.json()
#
#         user = db.history.find_one({"email": email})
#
#         if user:
#             # If user exists, update their history with an incrementing index
#             index = user.get("history_count", 0) + 1  # Increment index
#             history_item = {
#                 "index": index,
#                 "data": data,
#             }
#
#             # Update user information in the database
#             result = db.history.update_one(
#                 {"email": email},
#                 {"$push": {"history": history_item}, "$inc": {"history_count": 1}}
#             )
#
#             if result.modified_count == 1:
#                 return JSONResponse(content={"message": "User history created successfully", "index": index}, status_code=200)
#             else:
#                 raise HTTPException(status_code=500, detail="Failed to update user history")
#         else:
#             # If user not found, create a new entry
#             index = 1
#             history_item = {
#                 "index": index,  # Start index from 1
#                 "data": data
#             }
#
#             db.history.insert_one({
#                 "email": email,
#                 "history": [history_item],
#                 "history_count": 1
#             })
#
#             return JSONResponse(content={"message": "User history created successfully", "index": index}, status_code=200)
#
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@app.delete("/remove-from-history/{email}/{index}")
async def remove_from_history(email: str, index: int):
    try:
        user = db.history.find_one({"email": email})

        if user:
            result = db.history.update_one(
                {"email": email},
                {"$pull": {"history": {"index": index}}}
            )

            if result.modified_count == 1:
                return JSONResponse(content={"message": f"Item at index {index} removed from user history "
                                                        f"successfully"}, status_code=200)

            else:
                raise HTTPException(status_code=500, detail="Failed to remove item from user history")

        else:
            raise HTTPException(status_code=404, detail="User not found")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get-user-history/{email}")
async def get_user_history(email: str):
    try:
        # Query the database to find the user by email
        users = history_collection.find({"email": email})

        # If user is found, return user data as JSON
        if users:
            for user in users:
                user["_id"] = str(user["_id"])
                if "history" in user:
                    user = user["history"]
                else:
                    raise HTTPException(status_code=404, detail="History not found")
                return JSONResponse(content=user, status_code=200)
        else:
            raise HTTPException(status_code=404, detail="User not found")
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
                'stars': data['stars'],
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


def get_templates(vacation_type: str):
    try:
        templates = templates_collection.find({"vacationType": vacation_type})

        additional_data_template = additionalData_collection.find_one({"vacationType": vacation_type})

        # If template is found, return template data as JSON
        if templates:
            for temp in templates:
                new_index = (temp.get("index", 0) + 1) % 10  # Get the current index or default to 0 if it doesn't exist
                templates_collection.update_one(
                    {"_id": temp["_id"]},
                    {"$set": {"index": new_index}}
                )
                temp["_id"] = str(temp["_id"])
                temp = temp["template"]
                return set_data_to_templates(temp, additional_data_template, vacation_type, new_index)

        else:
            raise HTTPException(status_code=404, detail="Template not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def set_data_to_templates(template: str, additional_data_template, vacation_type: str, index):
    try:
        if index == 9:
            analyze_data(vacation_type)
        if user_details['anotherCityChecked'] and not user_details['returnCountry'] == '':
            template += f"We would like to return from the country {user_details['returnCountry']}. " \
                        f"When the trip will include travel to this country. "
        if not user_details['cities'] == []:
            template += f"In {user_details['destCountry']} we would like to travel in the cities " \
                        f"{user_details['cities']}. "
        if not user_details['adultsAmount'] is None:
            if vacation_type == "Couple Vacation":
                amount = user_details['adultsAmount'] * 2
                template += f"We are {amount} adults. "
            else:
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

                # Define the additional data to push
                data = additional
                result = additionalData_collection.update_one(
                    {"_id": additional_data_template["_id"]},
                    {"$push": {"data": data}}
                )

        # Replace placeholders with variables
        formatted_trip_details = template.format(ages=user_details['ages'], date1=str(user_details['dates'][0]),
                                                 date2=str(user_details['dates'][1]),
                                                 from_country=user_details['originCountry'],
                                                 to_country=user_details['destCountry'],
                                                 budget1=str(user_details['budget'][0]),
                                                 budget2=str(user_details['budget'][1]),
                                                 stars=str(user_details['stars']))

        formatted_trip_details += "Please prepare a vacation plan." + get_instructions()
        return formatted_trip_details

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def assist_analyze_data(user_message):
    try:
        gpt_response = openai.chat.completions.create(
            model="gpt-4-turbo",  # Specify the GPT model
            messages=[
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            temperature=1,
            max_tokens=2500,
        )

        response = gpt_response.choices[0].message.content.strip()
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def analyze_data(vacation_type: str):
    try:
        additional_data_template = additionalData_collection.find_one({"vacationType": vacation_type})

        if additional_data_template:
            response = assist_analyze_data("Please review the array: " + str(additional_data_template['data']) +
                                           " If you find something that returns many times, just send it back,"
                                           " without any other words. if didn't found - return 'NOT FOUND'")
            if not response == 'NOT FOUND':
                templates = templates_collection.find_one({"vacationType": vacation_type})
                templates_collection.update_one(
                    {"_id": templates["_id"]},
                    {"$set": {"template": templates["template"] + " In addition, " + response}}
                )

                additionalData_collection.update_one(
                    {"_id": additional_data_template["_id"]},
                    {"$set": {"data": []}}
                )

        else:
            raise HTTPException(status_code=404, detail="Template not found")

    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))


@app.put("/update-general-template")
async def update_general_template(request: Request):
    try:
        # Parse request JSON data
        data = await request.json()

        # Extract the new general-template value from the request data
        new_template = data.get("general-template")

        # Check if the new_template is provided
        if new_template is None:
            raise HTTPException(status_code=400, detail="New general-template value is missing")

        # Remove general-template from data to avoid updating it separately
        data.pop("general-template", None)

        # Update general-template in the database along with other information
        result = db.templates.update_one({}, {"$set": {"general-template": new_template, **data}})

        if result.modified_count == 1:
            return {"message": "General template updated successfully"}
        else:
            raise HTTPException(status_code=404, detail="No general-template field found in the database")

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Run the FastAPI application with Uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0")
