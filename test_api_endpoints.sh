#!/bin/bash

# Test API endpoints with user filtering
# This simulates requests coming from the API Gateway

BASE_URL="http://localhost:8000"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=================================================="
echo "Testing Recommendation Service API Endpoints"
echo "=================================================="
echo ""

# Function to generate HMAC signature (simplified - you'll need the real one from gateway)
generate_signature() {
    local timestamp=$(date +%s%N)
    local service_name="recommendation-service"
    local encrypt_key="${service_name}:${timestamp}"
    local secret="${GATEWAY_SECRET_KEY}"

    # Generate HMAC SHA256 signature
    signature=$(echo -n "${encrypt_key}" | openssl dgst -sha256 -hmac "${secret}" | cut -d' ' -f2)

    echo "${timestamp}|${signature}"
}

echo -e "${BLUE}📋 Test 1: Get projects for user-001${NC}"
echo "GET /recommendations/projects"
echo "Simulating: X-User-Id: user-001"
echo ""

# Get timestamp and signature
read timestamp signature <<< $(echo $(generate_signature) | tr '|' ' ')

curl -s -X GET "${BASE_URL}/recommendations/projects" \
  -H "X-Gateway-Signature: ${signature}" \
  -H "X-Gateway-Timestamp: ${timestamp}" \
  -H "X-Service-Name: recommendation-service" \
  -H "X-User-Id: user-001" | jq '.'

echo ""
echo "=================================================="
echo ""

echo -e "${BLUE}📋 Test 2: Get projects for user-002${NC}"
echo "GET /recommendations/projects"
echo "Simulating: X-User-Id: user-002"
echo ""

read timestamp signature <<< $(echo $(generate_signature) | tr '|' ' ')

curl -s -X GET "${BASE_URL}/recommendations/projects" \
  -H "X-Gateway-Signature: ${signature}" \
  -H "X-Gateway-Timestamp: ${timestamp}" \
  -H "X-Service-Name: recommendation-service" \
  -H "X-User-Id: user-002" | jq '.'

echo ""
echo "=================================================="
echo ""

echo -e "${BLUE}📋 Test 3: Get all recommendations for user-001${NC}"
echo "GET /recommendations"
echo "Simulating: X-User-Id: user-001"
echo ""

read timestamp signature <<< $(echo $(generate_signature) | tr '|' ' ')

curl -s -X GET "${BASE_URL}/recommendations?page=1&page_size=10" \
  -H "X-Gateway-Signature: ${signature}" \
  -H "X-Gateway-Timestamp: ${timestamp}" \
  -H "X-Service-Name: recommendation-service" \
  -H "X-User-Id: user-001" | jq '.'

echo ""
echo "=================================================="
echo ""

echo -e "${BLUE}📋 Test 4: Get recommendations for user-001, project proj-001${NC}"
echo "GET /recommendations?project_id=proj-001"
echo "Simulating: X-User-Id: user-001"
echo ""

read timestamp signature <<< $(echo $(generate_signature) | tr '|' ' ')

curl -s -X GET "${BASE_URL}/recommendations?project_id=proj-001&page=1&page_size=10" \
  -H "X-Gateway-Signature: ${signature}" \
  -H "X-Gateway-Timestamp: ${timestamp}" \
  -H "X-Service-Name: recommendation-service" \
  -H "X-User-Id: user-001" | jq '.'

echo ""
echo "=================================================="
echo ""

echo -e "${BLUE}📋 Test 5: Security Test - user-001 trying to access proj-004 (belongs to user-002)${NC}"
echo "GET /recommendations?project_id=proj-004"
echo "Simulating: X-User-Id: user-001"
echo "Expected: 0 results (user-001 has no access to proj-004)"
echo ""

read timestamp signature <<< $(echo $(generate_signature) | tr '|' ' ')

curl -s -X GET "${BASE_URL}/recommendations?project_id=proj-004&page=1&page_size=10" \
  -H "X-Gateway-Signature: ${signature}" \
  -H "X-Gateway-Timestamp: ${timestamp}" \
  -H "X-Service-Name: recommendation-service" \
  -H "X-User-Id: user-001" | jq '.'

echo ""
echo "=================================================="
echo ""

echo -e "${GREEN}✅ All tests completed!${NC}"
echo ""
echo "Note: If you see authentication errors, make sure:"
echo "  1. GATEWAY_SECRET_KEY is set in .env"
echo "  2. The service is running (python app.py or uvicorn app:app)"
echo "  3. Test data exists (run: python test_user_filtering.py first)"
