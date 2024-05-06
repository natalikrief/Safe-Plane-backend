import unittest
from fastapi.testclient import TestClient
from FastAPI import app, get_db


class TestEndpoints(unittest.TestCase):
    # test generate response - valid and invalid
    def setUp(self):
        self.client = TestClient(app)

    def test_generate_response_with_valid_data(self):
        # Test ID: Successful generation
        # Description: Generate a response with valid data
        # Expected results: Status code: 200
        # Observed results: Pass - Status code: 200 is received
        data = {
            "vacationType": "Family Vacation",
            "originCountry": "Israel",
            "destCountry": "Budapest",
            "dates": [08.05,12.05],
            "ages": "3-7",
            "returnCountry": "As destination country",
            "budget": [9000, 15000],
            "hotel": "in the center",
            "stars": "4",
            "parking": "",
            "beach": "include good vibe beach",
            "restaurants": "includes good restaurants",
            "bars": "",
            "cities": "",
            "carRentalCompany": "",
            "dietaryPreferences": "",
            "additionalData": ["attraction for kids"],
            "adultsAmount": 2,
            "childrenAmount": 2
        }
        response = self.client.post("/generate-response?email=natali", json=data)
        self.assertEqual(response.status_code, 200)

    def test_generate_response_with_invalid_data(self):
        # Test ID: Unsuccessful generation
        # Description: Generate a response with invalid data
        # Expected results: Status code: 500
        # Observed results: Pass – "vacationType" message is displayed. Missing argument.
        data = {"invalid_key": "invalid_value"}  # Add invalid input data
        response = self.client.post("/generate-response?email=natali", json=data)
        self.assertIn("500: 'vacationType'", response.text)

    def test_check_credentials_with_valid_credentials(self):
        # Test ID: Successful login
        # Description: Check credentials with valid credentials.
        # Expected results: Status code: 200
        # Observed results: Pass - Status code: 200 is received. "Credentials are valid" message is displayed.
        data = {"email": "natali@gmail.com", "password": "111111"}
        response = self.client.post("/check-credentials", json=data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Credentials are valid", response.text)

    def test_check_credentials_with_invalid_credentials(self):
        # Test ID: Unsuccessful login
        # Description: Check credentials with invalid credentials.
        # Expected results: Status code: 401
        # Observed results: Pass - "Invalid credentials" message is displayed.
        data = {"email": "natali@gmail.com", "password": "invalid_password"}
        response = self.client.post("/check-credentials", json=data)
        self.assertIn("Invalid credentials", response.text)


class TestDatabase(unittest.TestCase):
    # test DB connection + add/get/update user + add to history
    def setUp(self):
        self.db = next(get_db())
        self.client = TestClient(app)

    def test_database_connection(self):
        # Test ID: DB connection
        # Description: Test database connection.
        # Expected results: Database connection is not None.
        # Observed results: Pass - Database connection is found, Database name: 'safeplan'.
        self.assertIsNotNone(self.db)
        self.assertEqual(self.db.name, "safeplan")

    def test_user_crud_operations(self):
        # Test ID: CRUD operations
        # Description: User CRUD operations - Adding existent user.
        # Expected results: Status code: 400
        # Observed results: Pass – "Email already exists" message is displayed.
        user_data = {"email": "natali@gmail.com", "password": "123456", "fullName": "Natali K", "terms": True}
        response = self.client.post("/add-user", json=user_data)
        self.assertIn("Email already exists", response.text)

    def test_get_user(self):
        # Test ID: Successful fetching data from DB
        # Description: Get user information.
        # Expected results: Status code: 200
        # Observed results: Pass - Status code: 200 is received, with user's information.
        response = self.client.get("/get-user/natali@gmail.com")
        self.assertEqual(response.status_code, 200)
        self.assertIn('"email":"natali@gmail.com"', response.text)

    def test_update_user(self):
        # Test ID: Successful updating data in DB
        # Description: Update user information.
        # Expected results: Status code: 200
        # Observed results: Pass - Status code: 200 is received, user's information  is updated.
        update_data = {"fullName": "Natali Krief"}
        response = self.client.put("/update-user/natali@gmail.com", json=update_data)
        self.assertEqual(response.status_code, 200)
        self.assertIn('{"message":"User updated successfully"}', response.text)

        # Verify the change
        response = self.client.get("/get-user/natali@gmail.com")
        self.assertEqual(response.status_code, 200)
        self.assertIn('"fullName":"Natali Krief"', response.text)

        # Test updating user - return to source
        update_data = {"fullName": "Natali K"}
        response = self.client.put("/update-user/natali@gmail.com", json=update_data)
        self.assertEqual(response.status_code, 200)
        self.assertIn('{"message":"User updated successfully"}', response.text)

        # Verify the change
        response = self.client.get("/get-user/natali@gmail.com")
        self.assertEqual(response.status_code, 200)
        self.assertIn('"fullName":"Natali K"', response.text)

    def test_add_to_history(self):
        # Test ID: Successful updating history in DB
        # Description: Add plan to user history.
        # Expected results: Status code: 200
        # Observed results: Pass - Status code: 200 is received, user's plan updated to history collection.

        # First - get a plan:
        response = self.client.get("/get-user-history/natali")
        self.assertEqual(response.status_code, 200)
        import json
        response_list = json.loads(response.text)
        plan = response_list[0]['data']

        # Second - add the plan to user history
        response = self.client.put("/update-user-history/natali@gmail.com", json=plan)
        self.assertEqual(response.status_code, 200)
        self.assertIn('{"message":"User history updated successfully"}', response.text)


class TestDependencies(unittest.TestCase):
    # test DB connection + openapi url/version
    def test_get_db(self):
        # Test get_db dependency function
        db = next(get_db())
        self.assertIsNotNone(db)

    def test_openapi_url(self):
        # Test ID: OpenAPI URL
        # Description: Test openAPI URL property.
        # Expected results: OpenAPI URL is "/openapi.json".
        # Observed results: Pass – correct URL is displayed.
        self.assertEqual(app.openapi_url, "/openapi.json")

    def test_openapi_version(self):
        # Test ID: OpenAPI version
        # Description: Test openAPI version property.
        # Expected results: OpenAPI version is '3.1.0'.
        # Observed results: Pass - correct version is displayed.
        self.assertEqual(app.openapi_version, "3.1.0")


if __name__ == '__main__':
    unittest.main()
