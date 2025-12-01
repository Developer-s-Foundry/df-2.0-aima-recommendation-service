# Testing Guide: User & Project Filtering

This guide will help you test the new user and project filtering functionality.

## Prerequisites

1. Make sure you have the `.env` file configured (you already have this ✅)
2. Python 3.x installed
3. Dependencies installed: `pip install -r requirements.txt` (if you have one)

## Step 1: Reset the Database (IMPORTANT!)

The database schema has changed, so you need to delete the old database:

```bash
# Delete the old database
rm -f data/recommendations.db

# The new schema will be created automatically when you run the tests
```

## Step 2: Run Database-Level Tests (No API Required)

This tests the storage layer directly without starting the API server:

```bash
python test_user_filtering.py
```

**What this tests:**
- ✅ Database schema with user_id and project_id columns
- ✅ Storing recommendations with user and project info
- ✅ Filtering recommendations by user_id
- ✅ Filtering recommendations by project_id
- ✅ Security isolation (users can't see other users' data)

**Expected output:**
```
🧪 TESTING USER AND PROJECT FILTERING
📝 Adding test data...
  ✓ Added: user=user-001, project=proj-001, type=system.cpu
  ✓ Added: user=user-001, project=proj-001, type=system.memory
  ...

TEST 1: Get Projects for Each User
🔍 User: user-001
   Projects: 3
   - proj-001: 2 recommendations
   - proj-002: 1 recommendations
   - proj-003: 1 recommendations

TEST 4: Security - User Isolation
   user-001: 4 recommendations (expected: 4) ✅
   user-002: 3 recommendations (expected: 3) ✅
   user-003: 1 recommendations (expected: 1) ✅
   Security test PASSED - Users are properly isolated! ✅
```

## Step 3: Run API-Level Tests (With Simulated Auth)

This tests the API endpoints by simulating what the gateway would send:

```bash
python test_api_simple.py
```

**What this tests:**
- ✅ GET /recommendations/projects endpoint
- ✅ GET /recommendations endpoint (all projects)
- ✅ GET /recommendations?project_id=xxx endpoint (specific project)
- ✅ Security: Users accessing projects they don't own

**Expected output:**
```
TEST 1: User-001 (Multiple Projects)
🔍 Scenario: Get all recommendations for user-001
   User ID: user-001

   📁 User's Projects (3):
      • proj-001: 2 recommendations
      • proj-002: 1 recommendations
      • proj-003: 1 recommendations

   📊 Recommendations Found: 4
      • [system.cpu] Project: proj-001
      • [system.memory] Project: proj-001
      ...

TEST 5: Security Check
🔍 Scenario: User-001 trying to access proj-004 (belongs to user-002)
   📊 Recommendations Found: 0  ✅ SECURITY WORKING!
```

## Step 4: Test with Real API Server (Optional)

If you want to test the actual HTTP endpoints:

### 4.1: Start the API server

```bash
# In terminal 1
python app.py

# Or using uvicorn
uvicorn app:app --reload
```

### 4.2: Test with curl (Manual Testing)

**Note:** The API requires gateway authentication. For testing without the real gateway, you need to either:
1. Temporarily disable auth (set `GATEWAY_SECRET_KEY=""` in .env)
2. Or generate valid HMAC signatures

**Test 1: Get projects (with auth disabled)**
```bash
curl http://localhost:8000/recommendations/projects
```

**Test 2: Get all recommendations**
```bash
curl http://localhost:8000/recommendations
```

**Test 3: Get recommendations for specific project**
```bash
curl http://localhost:8000/recommendations?project_id=proj-001
```

## Step 5: Test with Real Events (RabbitMQ)

If you want to test with the actual event consumer:

### 5.1: Update mock_events.json to include user_id

The mock events already have `project_id`, but they need `user_id`. Edit a few events:

```json
{
  "user_id": "user-001",     ← ADD THIS
  "project_id": "proj-001",
  "type": "system.cpu",
  "timestamp": "2025-11-23T12:00:00Z",
  ...
}
```

### 5.2: Publish events to RabbitMQ

If you have a script that publishes mock events to RabbitMQ, run it:

```bash
# This depends on how you publish events
# Example:
python publish_mock_events.py
```

### 5.3: Start the consumer

```bash
python consumer.py
```

You should see output like:
```
🕒 2025-11-23T12:00:00Z | [user:user-001] [proj:proj-001] processed event [system.cpu] → 1 recommendation(s)
```

## Expected Results Summary

| User      | Projects           | Total Recommendations |
|-----------|-------------------|-----------------------|
| user-001  | proj-001, 002, 003| 4                     |
| user-002  | proj-002, 004     | 3                     |
| user-003  | proj-005          | 1                     |

### Security Tests:
- ✅ user-001 + proj-004 filter → 0 results (proj-004 belongs to user-002)
- ✅ user-002 + proj-001 filter → 0 results (proj-001 belongs to user-001)
- ✅ user-999 (non-existent) → 0 results

## Troubleshooting

### Issue: "column user_id not found"
**Solution:** Delete the old database:
```bash
rm data/recommendations.db
```

### Issue: "Gateway secret not configured"
**Solution:** Make sure GATEWAY_SECRET_KEY is set in .env

### Issue: "Authentication failed"
**Solution:** For local testing, you can temporarily disable auth by commenting out the auth check or setting GATEWAY_SECRET_KEY=""

### Issue: No recommendations returned
**Solution:** Make sure test data was added. Run:
```bash
python test_user_filtering.py
```

## Next Steps

Once all tests pass:

1. ✅ Contact the authentication team to confirm they're sending `X-User-Id` header
2. ✅ Ask them to add `user_id` field to all events published to RabbitMQ
3. ✅ Deploy and test with real authentication
4. ✅ Verify with the frontend team that they can consume the endpoints

## API Endpoints Reference

### GET /recommendations/projects
Returns all projects that have recommendations for the authenticated user.

**Response:**
```json
{
  "user_id": "user-001",
  "project_count": 3,
  "projects": [
    {
      "project_id": "proj-001",
      "recommendation_count": 2,
      "latest_timestamp": "2025-11-23T12:05:00Z"
    }
  ]
}
```

### GET /recommendations
Returns all recommendations for the authenticated user (across all projects).

**Query Parameters:**
- `page` (default: 1)
- `page_size` (default: 50, max: 200)
- `project_id` (optional) - filter by specific project
- `event_type` (optional) - filter by event type
- `since` (optional) - filter by timestamp

**Response:**
```json
{
  "page": 1,
  "page_size": 50,
  "total": 4,
  "pages": 1,
  "user_id": "user-001",
  "project_id": null,
  "items": [...]
}
```

### GET /recommendations?project_id=proj-001
Returns recommendations for the authenticated user for a specific project.

**Response:** Same as above, but filtered by project_id.
