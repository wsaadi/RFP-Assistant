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
"""
import argparse
import asyncio
import json
import os
import sys

# Allow running as `python -m loadtest.cli` from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loadtest.metrics import MetricsCollector
from loadtest.scenarios import run_concurrent_users
from loadtest.fixtures.generate_fixtures import main as generate_fixtures


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
    return parser.parse_args()


def main():
    args = parse_args()

    if args.generate_fixtures:
        generate_fixtures()
        return

    # Ensure fixtures exist
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    required_files = ["sample_rfp.pdf", "sample_old_rfp.pdf", "sample_response.docx", "sample_old_response.docx"]
    missing = [f for f in required_files if not os.path.exists(os.path.join(fixtures_dir, f))]
    if missing:
        print("  Generating test fixtures...")
        generate_fixtures()

    print("\n" + "=" * 72)
    print("  RFP ASSISTANT - LOAD TEST")
    print("=" * 72)
    print(f"  Target:         {args.url}")
    print(f"  Concurrent users: {args.users}")
    print(f"  Think time:     {args.think_time[0]}s - {args.think_time[1]}s")
    print(f"  Stagger delay:  {args.stagger}s")
    print(f"  Admin:          {args.admin_email}")
    print("=" * 72)

    collector = MetricsCollector()

    try:
        asyncio.run(
            run_concurrent_users(
                num_users=args.users,
                base_url=args.url.rstrip("/"),
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
