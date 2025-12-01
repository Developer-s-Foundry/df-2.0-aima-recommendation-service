#!/usr/bin/env python3
"""
Test script for user and project filtering functionality.

This script:
1. Adds test data with user_id and project_id
2. Tests the filtering endpoints
3. Verifies security (users can't see other users' data)
"""

import json
import time
from storage import init_db, store_recommendation, query_recommendations_paginated, get_user_projects

def add_test_data():
    """Add test recommendations with different users and projects."""
    print("📝 Adding test data...")

    test_recommendations = [
        # User 1 - Projects 1, 2, 3
        {
            "timestamp": "2025-11-23T12:00:00Z",
            "source": "test",
            "event_type": "system.cpu",
            "user_id": "user-001",
            "project_id": "proj-001",
            "recommendations": ["CPU usage high on proj-001"]
        },
        {
            "timestamp": "2025-11-23T12:05:00Z",
            "source": "test",
            "event_type": "system.memory",
            "user_id": "user-001",
            "project_id": "proj-001",
            "recommendations": ["Memory usage high on proj-001"]
        },
        {
            "timestamp": "2025-11-23T12:10:00Z",
            "source": "test",
            "event_type": "system.cpu",
            "user_id": "user-001",
            "project_id": "proj-002",
            "recommendations": ["CPU usage normal on proj-002"]
        },
        {
            "timestamp": "2025-11-23T12:15:00Z",
            "source": "test",
            "event_type": "system.disk",
            "user_id": "user-001",
            "project_id": "proj-003",
            "recommendations": ["Disk space low on proj-003"]
        },

        # User 2 - Projects 2, 4
        {
            "timestamp": "2025-11-23T12:20:00Z",
            "source": "test",
            "event_type": "system.cpu",
            "user_id": "user-002",
            "project_id": "proj-002",
            "recommendations": ["CPU usage high on proj-002 for user-002"]
        },
        {
            "timestamp": "2025-11-23T12:25:00Z",
            "source": "test",
            "event_type": "api.payment",
            "user_id": "user-002",
            "project_id": "proj-004",
            "recommendations": ["Payment API slow on proj-004"]
        },
        {
            "timestamp": "2025-11-23T12:30:00Z",
            "source": "test",
            "event_type": "system.memory",
            "user_id": "user-002",
            "project_id": "proj-004",
            "recommendations": ["Memory leak detected on proj-004"]
        },

        # User 3 - Project 5
        {
            "timestamp": "2025-11-23T12:35:00Z",
            "source": "test",
            "event_type": "system.net",
            "user_id": "user-003",
            "project_id": "proj-005",
            "recommendations": ["Network latency high on proj-005"]
        },
    ]

    for reco in test_recommendations:
        store_recommendation(reco)
        print(f"  ✓ Added: user={reco['user_id']}, project={reco['project_id']}, type={reco['event_type']}")

    print(f"\n✅ Added {len(test_recommendations)} test recommendations\n")


def test_get_user_projects():
    """Test getting projects for each user."""
    print("=" * 60)
    print("TEST 1: Get Projects for Each User")
    print("=" * 60)

    users = ["user-001", "user-002", "user-003"]

    for user_id in users:
        projects = get_user_projects(user_id=user_id)
        print(f"\n🔍 User: {user_id}")
        print(f"   Projects: {len(projects)}")
        for proj in projects:
            print(f"   - {proj['project_id']}: {proj['recommendation_count']} recommendations")

    print("\n" + "=" * 60 + "\n")


def test_get_all_user_recommendations():
    """Test getting all recommendations for a user (across all projects)."""
    print("=" * 60)
    print("TEST 2: Get All Recommendations for Each User")
    print("=" * 60)

    users = ["user-001", "user-002", "user-003"]

    for user_id in users:
        items, total = query_recommendations_paginated(
            page=1,
            page_size=50,
            user_id=user_id
        )
        print(f"\n🔍 User: {user_id}")
        print(f"   Total recommendations: {total}")
        for item in items:
            print(f"   - [{item['event_type']}] @ project_id from payload")

    print("\n" + "=" * 60 + "\n")


def test_get_project_specific_recommendations():
    """Test getting recommendations for specific user + project combinations."""
    print("=" * 60)
    print("TEST 3: Get Recommendations for Specific User + Project")
    print("=" * 60)

    test_cases = [
        ("user-001", "proj-001", 2),  # Should return 2
        ("user-001", "proj-002", 1),  # Should return 1
        ("user-002", "proj-002", 1),  # Should return 1 (different user, same project)
        ("user-002", "proj-004", 2),  # Should return 2
        ("user-001", "proj-004", 0),  # Should return 0 (user-001 has no access to proj-004)
    ]

    for user_id, project_id, expected_count in test_cases:
        items, total = query_recommendations_paginated(
            page=1,
            page_size=50,
            user_id=user_id,
            project_id=project_id
        )
        status = "✅" if total == expected_count else "❌"
        print(f"\n{status} User: {user_id}, Project: {project_id}")
        print(f"   Expected: {expected_count}, Got: {total}")
        if total != expected_count:
            print(f"   ⚠️  MISMATCH!")

    print("\n" + "=" * 60 + "\n")


def test_security_isolation():
    """Test that users cannot see other users' data."""
    print("=" * 60)
    print("TEST 4: Security - User Isolation")
    print("=" * 60)

    # User 1 should only see their own data
    user1_items, user1_total = query_recommendations_paginated(
        page=1, page_size=50, user_id="user-001"
    )

    # User 2 should only see their own data
    user2_items, user2_total = query_recommendations_paginated(
        page=1, page_size=50, user_id="user-002"
    )

    # User 3 should only see their own data
    user3_items, user3_total = query_recommendations_paginated(
        page=1, page_size=50, user_id="user-003"
    )

    print(f"\n🔒 User Isolation Test:")
    print(f"   user-001: {user1_total} recommendations (expected: 4)")
    print(f"   user-002: {user2_total} recommendations (expected: 3)")
    print(f"   user-003: {user3_total} recommendations (expected: 1)")

    total_isolated = user1_total + user2_total + user3_total
    print(f"\n   Total across all users: {total_isolated} (expected: 8)")

    if user1_total == 4 and user2_total == 3 and user3_total == 1:
        print("\n   ✅ Security test PASSED - Users are properly isolated!")
    else:
        print("\n   ❌ Security test FAILED - Check filtering logic!")

    print("\n" + "=" * 60 + "\n")


def run_all_tests():
    """Run all tests."""
    print("\n" + "🧪 " * 20)
    print("TESTING USER AND PROJECT FILTERING")
    print("🧪 " * 20 + "\n")

    # Initialize database
    print("🔧 Initializing database...")
    init_db()
    print("✅ Database initialized\n")

    # Add test data
    add_test_data()

    # Run tests
    test_get_user_projects()
    test_get_all_user_recommendations()
    test_get_project_specific_recommendations()
    test_security_isolation()

    print("🎉 " * 20)
    print("ALL TESTS COMPLETED!")
    print("🎉 " * 20 + "\n")


if __name__ == "__main__":
    run_all_tests()
