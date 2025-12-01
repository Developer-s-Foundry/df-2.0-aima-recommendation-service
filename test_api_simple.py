#!/usr/bin/env python3
"""
Simple API test script that bypasses authentication for local testing.

This directly calls the API endpoint functions to test filtering logic
without worrying about HMAC signatures.
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage import init_db, store_recommendation, query_recommendations_paginated, get_user_projects

def setup_test_data():
    """Create test data with users and projects."""
    print("🔧 Setting up test database...")
    init_db()

    print("📝 Adding test recommendations...")

    test_data = [
        # User 1 - has access to proj-001, proj-002, proj-003
        {"timestamp": "2025-11-23T10:00:00Z", "source": "test", "event_type": "system.cpu",
         "user_id": "user-001", "project_id": "proj-001",
         "recommendations": ["CPU at 85% on proj-001"]},

        {"timestamp": "2025-11-23T10:05:00Z", "source": "test", "event_type": "system.memory",
         "user_id": "user-001", "project_id": "proj-001",
         "recommendations": ["Memory usage high on proj-001"]},

        {"timestamp": "2025-11-23T10:10:00Z", "source": "test", "event_type": "system.cpu",
         "user_id": "user-001", "project_id": "proj-002",
         "recommendations": ["CPU normal on proj-002"]},

        {"timestamp": "2025-11-23T10:15:00Z", "source": "test", "event_type": "system.disk",
         "user_id": "user-001", "project_id": "proj-003",
         "recommendations": ["Disk space low on proj-003"]},

        # User 2 - has access to proj-002, proj-004
        {"timestamp": "2025-11-23T10:20:00Z", "source": "test", "event_type": "system.cpu",
         "user_id": "user-002", "project_id": "proj-002",
         "recommendations": ["CPU spike on proj-002"]},

        {"timestamp": "2025-11-23T10:25:00Z", "source": "test", "event_type": "api.payment",
         "user_id": "user-002", "project_id": "proj-004",
         "recommendations": ["Payment API timeout on proj-004"]},

        {"timestamp": "2025-11-23T10:30:00Z", "source": "test", "event_type": "system.memory",
         "user_id": "user-002", "project_id": "proj-004",
         "recommendations": ["Memory leak detected on proj-004"]},

        # User 3 - has access to proj-005 only
        {"timestamp": "2025-11-23T10:35:00Z", "source": "test", "event_type": "system.net",
         "user_id": "user-003", "project_id": "proj-005",
         "recommendations": ["High network latency on proj-005"]},
    ]

    for data in test_data:
        store_recommendation(data)

    print(f"✅ Added {len(test_data)} test recommendations\n")


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_scenario(description, user_id, project_id=None):
    """Test a specific scenario."""
    print(f"\n🔍 Scenario: {description}")
    print(f"   User ID: {user_id}")
    if project_id:
        print(f"   Project ID: {project_id}")
    print()

    # Get projects for this user
    projects = get_user_projects(user_id=user_id)
    print(f"   📁 User's Projects ({len(projects)}):")
    for proj in projects:
        print(f"      • {proj['project_id']}: {proj['recommendation_count']} recommendations")

    # Get recommendations
    items, total = query_recommendations_paginated(
        page=1,
        page_size=50,
        user_id=user_id,
        project_id=project_id
    )

    print(f"\n   📊 Recommendations Found: {total}")
    for item in items:
        payload = item.get('payload', {})
        project = payload.get('project_id', 'unknown')
        print(f"      • [{item['event_type']}] Project: {project}")


def run_tests():
    """Run all test scenarios."""
    print("\n" + "🧪 " * 30)
    print("   TESTING USER & PROJECT FILTERING")
    print("🧪 " * 30)

    setup_test_data()

    # Test 1: User with multiple projects
    print_section("TEST 1: User-001 (Multiple Projects)")
    test_scenario(
        "Get all recommendations for user-001",
        user_id="user-001"
    )

    # Test 2: Filter by specific project
    print_section("TEST 2: User-001 - Specific Project")
    test_scenario(
        "Get recommendations for user-001, project proj-001 only",
        user_id="user-001",
        project_id="proj-001"
    )

    # Test 3: Different user
    print_section("TEST 3: User-002 (Different Projects)")
    test_scenario(
        "Get all recommendations for user-002",
        user_id="user-002"
    )

    # Test 4: User with single project
    print_section("TEST 4: User-003 (Single Project)")
    test_scenario(
        "Get recommendations for user-003",
        user_id="user-003"
    )

    # Test 5: Security - User tries to access another user's project
    print_section("TEST 5: Security Check")
    test_scenario(
        "User-001 trying to access proj-004 (belongs to user-002)",
        user_id="user-001",
        project_id="proj-004"
    )
    print("\n   ⚠️  If 0 recommendations shown above, security is working! ✅")

    # Test 6: Non-existent user
    print_section("TEST 6: Non-Existent User")
    test_scenario(
        "Non-existent user-999",
        user_id="user-999"
    )
    print("\n   ⚠️  If 0 recommendations shown above, filtering is working! ✅")

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print("\n✅ Expected Results:")
    print("   • user-001 should see 4 recommendations (proj-001, proj-002, proj-003)")
    print("   • user-002 should see 3 recommendations (proj-002, proj-004)")
    print("   • user-003 should see 1 recommendation (proj-005)")
    print("   • user-001 + proj-004 should see 0 (security isolation)")
    print("   • user-999 should see 0 (non-existent user)")

    print("\n🎉 " * 35)
    print("\n")


if __name__ == "__main__":
    run_tests()
