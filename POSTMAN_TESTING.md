# Postman Testing Guide

This guide shows you how to test the user and project filtering endpoints using Postman.

## Setup

### 1. Start the Service

```bash
# Make sure your service is running
python app.py
# or
uvicorn app:app --reload
```

The service should be running on `http://localhost:8000`

### 2. Add Test Data

First, add some test data with user_id and project_id:

```bash
python test_api_simple.py
```

This will create test recommendations for:
- **user-001**: proj-001, proj-002, proj-003
- **user-002**: proj-002, proj-004
- **user-003**: proj-005

---

## Testing in Postman

### Important: Authentication Headers

Your API requires gateway authentication. For testing, you need to include these headers with EVERY request:

**Required Headers:**
```
X-Gateway-Signature: <generated_hmac_signature>
X-Gateway-Timestamp: <current_timestamp_in_nanoseconds>
X-Service-Name: recommendation-service
X-User-Id: <user_id_for_testing>
```

### Option A: Test with Auth Disabled (Recommended for Local Testing)

To make testing easier, you can temporarily disable authentication:

1. Open `.env` file
2. Comment out or remove the `GATEWAY_SECRET_KEY` line:
   ```
   # GATEWAY_SECRET_KEY=ahBee33wT7eyO4HddWnzq+H9yiz5cSd70RchhxM+jzaoxq7eWY3xob2gnBXACdVWVd+Z9TiGckiTuI5Fa0rYnw==
   ```
3. Restart your service

**⚠️ Remember to re-enable it before deploying!**

### Option B: Test with Auth Enabled (Real Scenario)

You'll need to generate the HMAC signature. Here's a Python script to help:

```python
import hmac
import hashlib
import time

def generate_auth_headers(user_id="user-001"):
    timestamp = str(int(time.time() * 1e9))  # nanoseconds
    service_name = "recommendation-service"
    secret = "ahBee33wT7eyO4HddWnzq+H9yiz5cSd70RchhxM+jzaoxq7eWY3xob2gnBXACdVWVd+Z9TiGckiTuI5Fa0rYnw=="

    encrypt_key = f"{service_name}:{timestamp}"
    signature = hmac.new(
        secret.encode('utf-8'),
        encrypt_key.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    print(f"X-Gateway-Signature: {signature}")
    print(f"X-Gateway-Timestamp: {timestamp}")
    print(f"X-Service-Name: {service_name}")
    print(f"X-User-Id: {user_id}")

generate_auth_headers("user-001")
```

---

## Test Cases for Postman

### Test 1: Get Projects for User-001

**Request:**
```
GET http://localhost:8000/recommendations/projects
```

**Headers (if auth disabled):**
```
X-User-Id: user-001
```

**Expected Response:**
```json
{
  "user_id": "user-001",
  "project_count": 3,
  "projects": [
    {
      "project_id": "proj-003",
      "recommendation_count": 1,
      "latest_timestamp": "2025-11-23T10:15:00Z"
    },
    {
      "project_id": "proj-002",
      "recommendation_count": 1,
      "latest_timestamp": "2025-11-23T10:10:00Z"
    },
    {
      "project_id": "proj-001",
      "recommendation_count": 2,
      "latest_timestamp": "2025-11-23T10:05:00Z"
    }
  ]
}
```

---

### Test 2: Get Projects for User-002

**Request:**
```
GET http://localhost:8000/recommendations/projects
```

**Headers:**
```
X-User-Id: user-002
```

**Expected Response:**
```json
{
  "user_id": "user-002",
  "project_count": 2,
  "projects": [
    {
      "project_id": "proj-004",
      "recommendation_count": 2,
      "latest_timestamp": "2025-11-23T10:30:00Z"
    },
    {
      "project_id": "proj-002",
      "recommendation_count": 1,
      "latest_timestamp": "2025-11-23T10:20:00Z"
    }
  ]
}
```

---

### Test 3: Get All Recommendations for User-001

**Request:**
```
GET http://localhost:8000/recommendations?page=1&page_size=50
```

**Headers:**
```
X-User-Id: user-001
```

**Expected Response:**
```json
{
  "page": 1,
  "page_size": 50,
  "total": 4,
  "pages": 1,
  "user_id": "user-001",
  "project_id": null,
  "items": [
    {
      "timestamp": "2025-11-23T10:15:00Z",
      "event_type": "system.disk",
      "source": "test",
      "payload": {
        "user_id": "user-001",
        "project_id": "proj-003",
        "recommendations": ["Disk space low on proj-003"]
      }
    },
    // ... 3 more items
  ]
}
```

---

### Test 4: Get Recommendations for User-001, Project proj-001

**Request:**
```
GET http://localhost:8000/recommendations?project_id=proj-001&page=1&page_size=50
```

**Headers:**
```
X-User-Id: user-001
```

**Expected Response:**
```json
{
  "page": 1,
  "page_size": 50,
  "total": 2,
  "pages": 1,
  "user_id": "user-001",
  "project_id": "proj-001",
  "items": [
    {
      "timestamp": "2025-11-23T10:05:00Z",
      "event_type": "system.memory",
      "source": "test",
      "payload": {
        "user_id": "user-001",
        "project_id": "proj-001",
        "recommendations": ["Memory usage high on proj-001"]
      }
    },
    {
      "timestamp": "2025-11-23T10:00:00Z",
      "event_type": "system.cpu",
      "source": "test",
      "payload": {
        "user_id": "user-001",
        "project_id": "proj-001",
        "recommendations": ["CPU at 85% on proj-001"]
      }
    }
  ]
}
```

---

### Test 5: Security Test - User-001 Trying to Access User-002's Project

**Request:**
```
GET http://localhost:8000/recommendations?project_id=proj-004&page=1&page_size=50
```

**Headers:**
```
X-User-Id: user-001
```

**Expected Response:**
```json
{
  "page": 1,
  "page_size": 50,
  "total": 0,
  "pages": 0,
  "user_id": "user-001",
  "project_id": "proj-004",
  "items": []
}
```

**✅ This proves security is working!** User-001 cannot see proj-004 (which belongs to user-002)

---

### Test 6: Filter by Event Type

**Request:**
```
GET http://localhost:8000/recommendations?event_type=system.cpu&page=1&page_size=50
```

**Headers:**
```
X-User-Id: user-001
```

**Expected Response:**
```json
{
  "page": 1,
  "page_size": 50,
  "total": 2,
  "pages": 1,
  "user_id": "user-001",
  "project_id": null,
  "items": [
    // Only CPU events for user-001
  ]
}
```

---

### Test 7: Pagination Test

**Request:**
```
GET http://localhost:8000/recommendations?page=1&page_size=2
```

**Headers:**
```
X-User-Id: user-001
```

**Expected Response:**
```json
{
  "page": 1,
  "page_size": 2,
  "total": 4,
  "pages": 2,
  "user_id": "user-001",
  "project_id": null,
  "items": [
    // Only 2 items (first page)
  ]
}
```

Then test page 2:
```
GET http://localhost:8000/recommendations?page=2&page_size=2
```

---

## Creating a Postman Collection

### Step 1: Create Collection

1. Open Postman
2. Click "New" → "Collection"
3. Name it "Recommendation Service - User Filtering"

### Step 2: Add Collection Variables

1. Click on your collection
2. Go to "Variables" tab
3. Add these variables:

| Variable | Initial Value | Current Value |
|----------|--------------|---------------|
| `base_url` | `http://localhost:8000` | `http://localhost:8000` |
| `user_id` | `user-001` | `user-001` |

### Step 3: Add Requests

For each test case above:

1. Click "Add Request"
2. Set the method (GET)
3. Set the URL using variables: `{{base_url}}/recommendations/projects`
4. Add headers:
   - Key: `X-User-Id`, Value: `{{user_id}}`
5. Save

### Step 4: Add Tests (Optional)

In the "Tests" tab of each request, you can add assertions:

```javascript
// Test for successful response
pm.test("Status code is 200", function () {
    pm.response.to.have.status(200);
});

// Test that user_id matches
pm.test("User ID matches request", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.user_id).to.eql(pm.variables.get("user_id"));
});

// Test that we got projects
pm.test("Has projects array", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.projects).to.be.an('array');
});
```

---

## Quick Testing Checklist

- [ ] Test 1: Get projects for user-001 → Should return 3 projects
- [ ] Test 2: Get projects for user-002 → Should return 2 projects
- [ ] Test 3: Get all recommendations for user-001 → Should return 4 items
- [ ] Test 4: Get recommendations for user-001 + proj-001 → Should return 2 items
- [ ] Test 5: Get recommendations for user-001 + proj-004 → Should return 0 items (security)
- [ ] Test 6: Get recommendations for user-002 + proj-004 → Should return 2 items
- [ ] Test 7: Pagination works correctly

---

## Troubleshooting

### Issue: "Gateway secret not configured on server"
**Solution:** Comment out `GATEWAY_SECRET_KEY` in `.env` for local testing

### Issue: "Invalid gateway signature"
**Solution:**
1. Either disable auth (comment out GATEWAY_SECRET_KEY)
2. Or use the Python script above to generate valid signatures

### Issue: "401 Unauthorized"
**Solution:** Make sure you're including the `X-User-Id` header

### Issue: Empty results
**Solution:** Make sure you ran `python test_api_simple.py` to add test data

### Issue: "user_id" is null in response
**Solution:** Make sure the `X-User-Id` header is being sent

---

## Export/Import Postman Collection

Save this as a `.json` file and import into Postman:

```json
{
  "info": {
    "name": "Recommendation Service - User Filtering",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "variable": [
    {
      "key": "base_url",
      "value": "http://localhost:8000"
    },
    {
      "key": "user_id",
      "value": "user-001"
    }
  ],
  "item": [
    {
      "name": "Get User Projects",
      "request": {
        "method": "GET",
        "header": [
          {
            "key": "X-User-Id",
            "value": "{{user_id}}"
          }
        ],
        "url": {
          "raw": "{{base_url}}/recommendations/projects",
          "host": ["{{base_url}}"],
          "path": ["recommendations", "projects"]
        }
      }
    },
    {
      "name": "Get All Recommendations",
      "request": {
        "method": "GET",
        "header": [
          {
            "key": "X-User-Id",
            "value": "{{user_id}}"
          }
        ],
        "url": {
          "raw": "{{base_url}}/recommendations?page=1&page_size=50",
          "host": ["{{base_url}}"],
          "path": ["recommendations"],
          "query": [
            {
              "key": "page",
              "value": "1"
            },
            {
              "key": "page_size",
              "value": "50"
            }
          ]
        }
      }
    },
    {
      "name": "Get Recommendations by Project",
      "request": {
        "method": "GET",
        "header": [
          {
            "key": "X-User-Id",
            "value": "{{user_id}}"
          }
        ],
        "url": {
          "raw": "{{base_url}}/recommendations?project_id=proj-001&page=1&page_size=50",
          "host": ["{{base_url}}"],
          "path": ["recommendations"],
          "query": [
            {
              "key": "project_id",
              "value": "proj-001"
            },
            {
              "key": "page",
              "value": "1"
            },
            {
              "key": "page_size",
              "value": "50"
            }
          ]
        }
      }
    }
  ]
}
```

Save this as `postman_collection.json` and import it into Postman!
