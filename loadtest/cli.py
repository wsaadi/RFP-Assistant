#!/usr/bin/env python3
"""
RFP Assistant Load Testing CLI

Simulates 1-10 concurrent users performing realistic end-to-end journeys:
  - Login & authentication
  - Document upload (PDF, DOCX)
  - Document processing & vector indexing
  - Semantic search across documents
  - AI-powered chapter structure generation
  - Manual chapter creation with sub-chapters
  - AI content generation per chapter
  - Compliance analysis (AI)
  - Word document export
  - Soutenance/defense material generation (AI)
  - Project cleanup

Usage:
  python -m loadtest.cli --users 3 --url http://localhost:8000
  python -m loadtest.cli --users 5 --url http://localhost:8000 --admin-email admin@rfp-assistant.fr --admin-password admin123 --think-time 1.0 3.0
  python -m loadtest.cli --users 1 --url http://localhost:8000 --json report.json

Cleanup:
  python -m loadtest.cli --cleanup --url http://localhost:8000 --admin-password secret
"""
import argparse
import asyncio
import json
import os
import sys

import httpx

# Allow running as `python -m loadtest.cli` from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loadtest.metrics import MetricsCollector
from loadtest.scenarios import run_concurrent_users
from loadtest.fixtures.generate_fixtures import main as generate_fixtures

# Prefix used by load test projects — NEVER touch projects without this prefix
LOADTEST_PROJECT_PREFIX = "LoadTest-User"
LOADTEST_USER_EMAIL_PATTERN = "loadtest_user"


def parse_args():
    parser = argparse.ArgumentParser(
        description="RFP Assistant Load Testing CLI - Simulate realistic user journeys",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Quick smoke test with 1 user
  python -m loadtest.cli --users 1 --url http://localhost:8000

  # Load test with 5 concurrent users
  python -m loadtest.cli --users 5 --url http://localhost:8000

  # Full stress test with 10 users, fast think time
  python -m loadtest.cli --users 10 --url http://localhost:8000 --think-time 0.1 0.5

  # Export results to JSON
  python -m loadtest.cli --users 3 --url http://localhost:8000 --json results.json

  # Generate test fixtures only
  python -m loadtest.cli --generate-fixtures

  # Clean up leftover LoadTest projects and test users
  python -m loadtest.cli --cleanup --url http://localhost:8000 --admin-password secret
""",
    )
    parser.add_argument(
        "--users", "-n",
        type=int,
        default=1,
        choices=range(1, 11),
        metavar="N",
        help="Number of concurrent users to simulate (1-10, default: 1)",
    )
    parser.add_argument(
        "--url", "-u",
        type=str,
        default="http://localhost:8000",
        help="Base URL of the RFP Assistant backend (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--admin-email",
        type=str,
        default="admin@rfp-assistant.fr",
        help="Admin email for creating test users (default: admin@rfp-assistant.fr)",
    )
    parser.add_argument(
        "--admin-password",
        type=str,
        default="admin123",
        help="Admin password (default: admin123)",
    )
    parser.add_argument(
        "--think-time",
        nargs=2,
        type=float,
        default=[0.5, 2.0],
        metavar=("MIN", "MAX"),
        help="Min and max think time between steps in seconds (default: 0.5 2.0)",
    )
    parser.add_argument(
        "--stagger",
        type=float,
        default=1.0,
        help="Delay in seconds between starting each user (default: 1.0)",
    )
    parser.add_argument(
        "--json", "-j",
        type=str,
        default=None,
        metavar="FILE",
        help="Export results as JSON to the specified file",
    )
    parser.add_argument(
        "--generate-fixtures",
        action="store_true",
        help="Generate sample test documents and exit",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete all LoadTest projects and loadtest_user accounts, then exit",
    )
    return parser.parse_args()


async def cleanup_loadtest_data(base_url: str, admin_email: str, admin_password: str):
    """Delete all LoadTest-* projects and loadtest_user* accounts.

    Safety: only touches resources whose names match load test patterns.
    Real user projects and accounts are NEVER modified.
    """
    base_url = base_url.rstrip("/")
    timeout = httpx.Timeout(connect=10, read=60, write=30, pool=10)

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Login as admin
        login_resp = await client.post(
            f"{base_url}/api/auth/login",
            json={"email": admin_email, "password": admin_password},
        )
        if login_resp.status_code != 200:
            print(f"  ERROR: Admin login failed ({login_resp.status_code})")
            return False
        token = login_resp.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        # --- Clean up projects ---
        print("\n  Scanning for LoadTest projects...")
        ws_resp = await client.get(f"{base_url}/api/workspaces")
        if ws_resp.status_code != 200:
            print(f"  ERROR: Cannot list workspaces ({ws_resp.status_code})")
            return False

        projects_deleted = 0
        for ws in ws_resp.json():
            ws_id = ws["id"]
            proj_resp = await client.get(f"{base_url}/api/projects/workspace/{ws_id}")
            if proj_resp.status_code != 200:
                continue
            for project in proj_resp.json():
                name = project.get("name", "")
                if not name.startswith(LOADTEST_PROJECT_PREFIX):
                    continue
                pid = project["id"]
                del_resp = await client.delete(f"{base_url}/api/projects/{pid}")
                if del_resp.status_code in (200, 204):
                    print(f"    Deleted project: {name}")
                    projects_deleted += 1
                else:
                    print(f"    Failed to delete {name}: HTTP {del_resp.status_code}")

        # --- Clean up test user accounts ---
        print("\n  Scanning for loadtest user accounts...")
        users_resp = await client.get(f"{base_url}/api/admin/users")
        users_deleted = 0
        if users_resp.status_code == 200:
            for user in users_resp.json():
                email = user.get("email", "")
                if LOADTEST_USER_EMAIL_PATTERN not in email:
                    continue
                uid = user["id"]
                del_resp = await client.delete(f"{base_url}/api/admin/users/{uid}")
                if del_resp.status_code in (200, 204):
                    print(f"    Deleted user: {email}")
                    users_deleted += 1
                else:
                    print(f"    Failed to delete {email}: HTTP {del_resp.status_code}")

        print(f"\n  Cleanup done: {projects_deleted} project(s), {users_deleted} user(s) removed.")
        return True


def main():
    args = parse_args()

    if args.generate_fixtures:
        generate_fixtures()
        return

    if args.cleanup:
        base_url = args.url.rstrip("/")
        print("\n" + "=" * 72)
        print("  RFP ASSISTANT - LOAD TEST CLEANUP")
        print("=" * 72)
        print(f"  Target:  {base_url}")
        print(f"  Filter:  projects starting with '{LOADTEST_PROJECT_PREFIX}'")
        print(f"           users matching '*{LOADTEST_USER_EMAIL_PATTERN}*'")
        print("=" * 72)
        asyncio.run(cleanup_loadtest_data(base_url, args.admin_email, args.admin_password))
        return

    # Ensure fixtures exist
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    required_files = ["sample_rfp.pdf", "sample_old_rfp.pdf", "sample_response.docx", "sample_old_response.docx"]
    missing = [f for f in required_files if not os.path.exists(os.path.join(fixtures_dir, f))]
    if missing:
        print("  Generating test fixtures...")
        generate_fixtures()

    base_url = args.url.rstrip("/")

    print("\n" + "=" * 72)
    print("  RFP ASSISTANT - LOAD TEST")
    print("=" * 72)
    print(f"  Target:         {base_url}")
    print(f"  Concurrent users: {args.users}")
    print(f"  Think time:     {args.think_time[0]}s - {args.think_time[1]}s")
    print(f"  Stagger delay:  {args.stagger}s")
    print(f"  Admin:          {args.admin_email}")
    print("=" * 72)

    # Pre-flight connectivity check
    print(f"\n  Checking connectivity to {base_url} ...")
    try:
        resp = httpx.get(f"{base_url}/api/health", timeout=10)
        print(f"  Health check: HTTP {resp.status_code}")
    except httpx.ConnectError:
        print(f"\n  ERROR: Cannot connect to {base_url}")
        print(f"  Make sure the backend is running (docker compose up, or uvicorn).")
        print(f"  If running inside Docker, use the host-accessible URL (e.g. http://localhost:8000).\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n  WARNING: Health check failed ({e}), proceeding anyway...\n")

    collector = MetricsCollector()

    try:
        asyncio.run(
            run_concurrent_users(
                num_users=args.users,
                base_url=base_url,
                admin_email=args.admin_email,
                admin_password=args.admin_password,
                collector=collector,
                stagger_delay=args.stagger,
                think_time=tuple(args.think_time),
            )
        )
    except KeyboardInterrupt:
        print("\n  Interrupted by user. Collecting partial results...")
        collector.stop()
    except Exception as e:
        print(f"\n  Fatal error: {e}")
        collector.stop()

    # Print report
    report = collector.print_report()

    # Export JSON if requested
    if args.json and report:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"  Results exported to: {args.json}")

    # Exit code based on verdict
    verdict = collector.verdict(report)
    sys.exit(0 if verdict["pass"] else 1)


if __name__ == "__main__":
    main()
