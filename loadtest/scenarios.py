"""Realistic user journey scenarios for load testing the RFP Assistant."""
import asyncio
import os
import time
import random
from typing import Optional

import httpx

from .metrics import MetricsCollector, RequestMetric, UserJourneyMetric

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Realistic chapter structures for RFP responses
CHAPTER_TEMPLATES = [
    {"title": "Presentation de la societe", "desc": "Historique, chiffres cles, references"},
    {"title": "Comprehension du besoin", "desc": "Analyse du cahier des charges et enjeux"},
    {"title": "Solution technique proposee", "desc": "Architecture, technologies, methodologie"},
    {"title": "Equipe projet", "desc": "Composition, competences, CV"},
    {"title": "Planning de realisation", "desc": "Phases, jalons, livrables"},
    {"title": "Offre financiere", "desc": "Decomposition des couts, conditions"},
    {"title": "Engagements qualite", "desc": "SLA, indicateurs, penalites"},
    {"title": "Maintenance et support", "desc": "Organisation, niveaux, GTR/GTI"},
]

SUB_CHAPTER_TEMPLATES = [
    {"title": "Contexte et enjeux", "desc": "Analyse du contexte client"},
    {"title": "Notre approche", "desc": "Methodologie et demarche"},
    {"title": "Livrables", "desc": "Documents et produits a fournir"},
    {"title": "Ressources mobilisees", "desc": "Profils et competences"},
]

# Search queries to simulate real user behavior
SEARCH_QUERIES = [
    "criteres d'evaluation",
    "budget previsionnel",
    "delais de livraison",
    "competences techniques requises",
    "references clients",
    "methodologie de projet",
    "garantie et maintenance",
    "formation utilisateurs",
    "migration de donnees",
    "securite des donnees",
]


class UserSession:
    """Simulates a single user's session against the RFP Assistant API."""

    def __init__(
        self,
        user_id: int,
        base_url: str,
        email: str,
        password: str,
        collector: MetricsCollector,
        think_time: tuple[float, float] = (0.5, 2.0),
    ):
        self.user_id = user_id
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.collector = collector
        self.think_time = think_time

        self.client: Optional[httpx.AsyncClient] = None
        self.token: Optional[str] = None
        self.workspace_id: Optional[str] = None
        self.project_id: Optional[str] = None
        self.chapter_ids: list[str] = []
        self.document_ids: list[str] = []

    async def _think(self):
        """Simulate human think time between actions."""
        delay = random.uniform(*self.think_time)
        await asyncio.sleep(delay)

    async def _request(
        self,
        step: str,
        method: str,
        path: str,
        **kwargs,
    ) -> tuple[httpx.Response | None, float]:
        """Make an HTTP request and record metrics."""
        url = f"{self.base_url}{path}"
        start = time.monotonic()
        resp = None
        error_msg = None

        try:
            resp = await self.client.request(method, url, **kwargs)
            duration = (time.monotonic() - start) * 1000
            success = 200 <= resp.status_code < 400
            if not success:
                try:
                    body = resp.json()
                    error_msg = body.get("detail", resp.text[:200])
                except Exception:
                    error_msg = resp.text[:200]
        except httpx.TimeoutException as e:
            duration = (time.monotonic() - start) * 1000
            success = False
            error_msg = f"Timeout: {e}"
        except httpx.ConnectError as e:
            duration = (time.monotonic() - start) * 1000
            success = False
            error_msg = f"Connection error: {e}"
        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            success = False
            error_msg = str(e)

        self.collector.record_request(RequestMetric(
            user_id=self.user_id,
            step=step,
            method=method,
            url=path,
            status_code=resp.status_code if resp else 0,
            duration_ms=duration,
            success=success,
            error=error_msg,
        ))

        return resp, duration

    async def run_full_journey(self):
        """Execute a complete realistic user journey."""
        journey = UserJourneyMetric(
            user_id=self.user_id,
            started_at=time.time(),
            steps_total=12,
        )

        timeout = httpx.Timeout(connect=10, read=120, write=30, pool=10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            self.client = client
            try:
                # Step 1: Login
                await self._step_login()
                journey.steps_completed += 1
                await self._think()

                # Step 2: List workspaces
                await self._step_list_workspaces()
                journey.steps_completed += 1
                await self._think()

                # Step 3: Create project
                await self._step_create_project()
                journey.steps_completed += 1
                await self._think()

                # Step 4: Upload documents (RFP + old response)
                await self._step_upload_documents()
                journey.steps_completed += 1
                await self._think()

                # Step 5: Wait for document processing
                await self._step_wait_processing()
                journey.steps_completed += 1
                await self._think()

                # Step 6: Search documents
                await self._step_search_documents()
                journey.steps_completed += 1
                await self._think()

                # Step 7: Generate chapter structure (AI call)
                await self._step_generate_structure()
                journey.steps_completed += 1
                await self._think()

                # Step 8: Create chapters manually
                await self._step_create_chapters()
                journey.steps_completed += 1
                await self._think()

                # Step 9: Generate chapter content (AI call)
                await self._step_generate_content()
                journey.steps_completed += 1
                await self._think()

                # Step 10: Run compliance analysis (AI call)
                await self._step_compliance_analysis()
                journey.steps_completed += 1
                await self._think()

                # Step 11: Export Word document
                await self._step_export_word()
                journey.steps_completed += 1
                await self._think()

                # Step 12: Generate soutenance (AI call)
                await self._step_generate_soutenance()
                journey.steps_completed += 1

                # Cleanup: delete project
                await self._step_cleanup()

                journey.success = True

            except Exception as e:
                journey.error = str(e)
                journey.success = False
                print(f"  [User {self.user_id}] Journey failed at step {journey.steps_completed + 1}: {e}")

            finally:
                journey.finished_at = time.time()
                self.collector.record_journey(journey)
                self.client = None

    async def _step_login(self):
        """Login and store token."""
        resp, _ = await self._request(
            "login", "POST", "/api/auth/login",
            json={"email": self.email, "password": self.password},
        )
        if resp and resp.status_code == 200:
            data = resp.json()
            self.token = data["access_token"]
            self.client.headers["Authorization"] = f"Bearer {self.token}"
            print(f"  [User {self.user_id}] Logged in as {self.email}")
        else:
            raise RuntimeError(f"Login failed: {resp.status_code if resp else 'no response'}")

    async def _step_list_workspaces(self):
        """List workspaces and pick the first one."""
        resp, _ = await self._request("list_workspaces", "GET", "/api/workspaces")
        if resp and resp.status_code == 200:
            workspaces = resp.json()
            if workspaces:
                self.workspace_id = workspaces[0]["id"]
                print(f"  [User {self.user_id}] Using workspace: {workspaces[0]['name']}")
            else:
                raise RuntimeError("No workspaces available")
        else:
            raise RuntimeError("Failed to list workspaces")

    async def _step_create_project(self):
        """Create a new RFP project."""
        project_name = f"LoadTest-User{self.user_id}-{int(time.time())}"
        resp, _ = await self._request(
            "create_project", "POST",
            f"/api/projects/workspace/{self.workspace_id}",
            json={
                "name": project_name,
                "description": "Projet de test de charge automatise",
                "client_name": f"Client Test {self.user_id}",
                "company_name": "Societe de Test",
                "rfp_reference": f"AO-LT-{self.user_id:03d}",
                "deadline": "2026-06-30",
            },
        )
        if resp and resp.status_code == 201:
            self.project_id = resp.json()["id"]
            print(f"  [User {self.user_id}] Created project: {project_name}")
        else:
            raise RuntimeError(f"Failed to create project: {resp.status_code if resp else 'no response'}")

    async def _step_upload_documents(self):
        """Upload sample PDF and DOCX documents."""
        uploads = [
            ("sample_rfp.pdf", "new_rfp"),
            ("sample_old_rfp.pdf", "old_rfp"),
            ("sample_response.docx", "old_response"),
            ("sample_old_response.docx", "inspiration"),
        ]

        for filename, category in uploads:
            filepath = os.path.join(FIXTURES_DIR, filename)
            if not os.path.exists(filepath):
                print(f"  [User {self.user_id}] Fixture not found: {filepath}, skipping")
                continue

            with open(filepath, "rb") as f:
                file_bytes = f.read()

            resp, _ = await self._request(
                "upload_document", "POST",
                f"/api/documents/upload/{self.project_id}",
                files={"file": (filename, file_bytes)},
                data={"category": category},
            )
            if resp and resp.status_code == 200:
                doc_id = resp.json()["id"]
                self.document_ids.append(doc_id)
                print(f"  [User {self.user_id}] Uploaded {filename} ({category})")
            else:
                status = resp.status_code if resp else "no response"
                print(f"  [User {self.user_id}] Upload failed for {filename}: {status}")

            await self._think()

    async def _step_wait_processing(self):
        """Poll document processing progress until complete or timeout."""
        max_wait = 120  # seconds
        poll_interval = 3
        start = time.monotonic()

        while (time.monotonic() - start) < max_wait:
            resp, _ = await self._request(
                "check_processing", "GET",
                f"/api/documents/progress/{self.project_id}",
            )
            if resp and resp.status_code == 200:
                progress = resp.json().get("progress", [])
                if not progress:
                    print(f"  [User {self.user_id}] Documents processed (no active processing)")
                    return
                all_done = all(
                    p.get("db_status") in ("completed", "failed") or p.get("progress", 0) == 100
                    for p in progress
                )
                if all_done:
                    print(f"  [User {self.user_id}] All documents processed")
                    return

            await asyncio.sleep(poll_interval)

        print(f"  [User {self.user_id}] Processing timeout after {max_wait}s (continuing anyway)")

    async def _step_search_documents(self):
        """Perform vector searches across the project documents."""
        queries = random.sample(SEARCH_QUERIES, min(3, len(SEARCH_QUERIES)))
        for query in queries:
            resp, _ = await self._request(
                "search_documents", "POST",
                f"/api/documents/search/{self.project_id}",
                json={"query": query, "top_k": 5},
            )
            if resp and resp.status_code == 200:
                results = resp.json().get("results", [])
                print(f"  [User {self.user_id}] Search '{query}': {len(results)} results")
            await self._think()

    async def _step_generate_structure(self):
        """Trigger AI-based chapter structure generation."""
        resp, _ = await self._request(
            "generate_structure", "POST",
            f"/api/projects/{self.project_id}/generate-structure",
            json={},
        )
        if resp and resp.status_code == 200:
            print(f"  [User {self.user_id}] Structure generation started")
            # Poll for completion
            await self._poll_progress("structure_status", f"/api/projects/{self.project_id}/generate-structure-status")
        else:
            status = resp.status_code if resp else "no response"
            print(f"  [User {self.user_id}] Structure generation: {status} (may require AI config)")

    async def _step_create_chapters(self):
        """Create chapters manually (fallback if AI structure gen not configured)."""
        templates = random.sample(CHAPTER_TEMPLATES, min(4, len(CHAPTER_TEMPLATES)))
        for i, tmpl in enumerate(templates):
            resp, _ = await self._request(
                "create_chapter", "POST",
                f"/api/chapters/project/{self.project_id}",
                json={
                    "title": tmpl["title"],
                    "description": tmpl["desc"],
                    "order": i,
                    "chapter_type": "chapter",
                },
            )
            if resp and resp.status_code == 201:
                chapter_id = resp.json()["id"]
                self.chapter_ids.append(chapter_id)
                print(f"  [User {self.user_id}] Created chapter: {tmpl['title']}")

                # Add a sub-chapter
                if SUB_CHAPTER_TEMPLATES and random.random() > 0.5:
                    sub = random.choice(SUB_CHAPTER_TEMPLATES)
                    sub_resp, _ = await self._request(
                        "create_sub_chapter", "POST",
                        f"/api/chapters/project/{self.project_id}",
                        json={
                            "title": sub["title"],
                            "description": sub["desc"],
                            "parent_id": chapter_id,
                            "order": 0,
                            "chapter_type": "sub_chapter",
                        },
                    )
                    if sub_resp and sub_resp.status_code == 201:
                        self.chapter_ids.append(sub_resp.json()["id"])

            await self._think()

    async def _step_generate_content(self):
        """Trigger AI content generation for chapters."""
        if not self.chapter_ids:
            print(f"  [User {self.user_id}] No chapters to generate content for")
            return

        # Generate content for up to 2 chapters (expensive AI operation)
        chapters_to_gen = self.chapter_ids[:2]
        for chapter_id in chapters_to_gen:
            resp, _ = await self._request(
                "generate_content", "POST",
                f"/api/chapters/{chapter_id}/generate-content",
                json={
                    "action": "generate",
                    "custom_prompt": "",
                    "use_old_response": True,
                    "include_improvement_axes": True,
                },
            )
            if resp and resp.status_code == 200:
                print(f"  [User {self.user_id}] Content generation launched for chapter")
                # Poll status
                await self._poll_chapter_gen(chapter_id)
            else:
                status = resp.status_code if resp else "no response"
                print(f"  [User {self.user_id}] Content gen: {status} (may need AI config)")

            await self._think()

    async def _step_compliance_analysis(self):
        """Run compliance analysis (AI-powered)."""
        resp, _ = await self._request(
            "compliance_analysis", "POST",
            f"/api/projects/{self.project_id}/compliance-analysis",
            json={},
        )
        if resp:
            print(f"  [User {self.user_id}] Compliance analysis: {resp.status_code}")
            if resp.status_code == 200:
                await self._poll_progress(
                    "compliance_status",
                    f"/api/projects/{self.project_id}/compliance-analysis-status",
                )
        else:
            print(f"  [User {self.user_id}] Compliance analysis: no response")

    async def _step_export_word(self):
        """Export project as Word document."""
        resp, _ = await self._request(
            "export_word", "POST",
            f"/api/export/{self.project_id}/word",
            json={},
        )
        if resp and resp.status_code == 200:
            print(f"  [User {self.user_id}] Word export started")
            # Poll status
            max_wait = 90
            start = time.monotonic()
            while (time.monotonic() - start) < max_wait:
                status_resp, _ = await self._request(
                    "export_word_status", "GET",
                    f"/api/export/{self.project_id}/word-status",
                )
                if status_resp and status_resp.status_code == 200:
                    data = status_resp.json()
                    if data.get("status") in ("completed", "ready"):
                        print(f"  [User {self.user_id}] Word export ready")
                        # Download
                        await self._request(
                            "download_word", "GET",
                            f"/api/export/{self.project_id}/word-download",
                        )
                        break
                    elif data.get("status") == "failed":
                        print(f"  [User {self.user_id}] Word export failed")
                        break
                await asyncio.sleep(3)
        else:
            status = resp.status_code if resp else "no response"
            print(f"  [User {self.user_id}] Word export: {status}")

    async def _step_generate_soutenance(self):
        """Generate soutenance/defense materials (AI-powered)."""
        resp, _ = await self._request(
            "generate_soutenance", "POST",
            f"/api/export/{self.project_id}/soutenance",
            json={},
        )
        if resp:
            print(f"  [User {self.user_id}] Soutenance generation: {resp.status_code}")
            if resp.status_code == 200:
                # Poll for completion
                max_wait = 120
                start = time.monotonic()
                while (time.monotonic() - start) < max_wait:
                    status_resp, _ = await self._request(
                        "soutenance_status", "GET",
                        f"/api/export/{self.project_id}/soutenance-status",
                    )
                    if status_resp and status_resp.status_code == 200:
                        data = status_resp.json()
                        if data.get("status") in ("completed", "ready", "idle"):
                            print(f"  [User {self.user_id}] Soutenance ready")
                            break
                        elif data.get("status") == "failed":
                            print(f"  [User {self.user_id}] Soutenance failed")
                            break
                    await asyncio.sleep(3)

    async def _step_cleanup(self):
        """Delete the test project to clean up."""
        if self.project_id:
            resp, _ = await self._request(
                "delete_project", "DELETE",
                f"/api/projects/{self.project_id}",
            )
            if resp and resp.status_code in (200, 204):
                print(f"  [User {self.user_id}] Cleaned up project")
            else:
                print(f"  [User {self.user_id}] Cleanup: {resp.status_code if resp else 'no response'}")

    async def _poll_progress(self, step_name: str, status_url: str, max_wait: int = 120):
        """Generic progress polling."""
        start = time.monotonic()
        while (time.monotonic() - start) < max_wait:
            resp, _ = await self._request(step_name, "GET", status_url)
            if resp and resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "")
                if status in ("completed", "ready", "idle"):
                    return
                if status == "failed":
                    return
            await asyncio.sleep(3)

    async def _poll_chapter_gen(self, chapter_id: str, max_wait: int = 120):
        """Poll chapter generation status."""
        start = time.monotonic()
        while (time.monotonic() - start) < max_wait:
            resp, _ = await self._request(
                "chapter_gen_status", "GET",
                f"/api/chapters/{chapter_id}/generate-status",
            )
            if resp and resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "")
                if status in ("completed", "idle"):
                    return
                if status == "failed":
                    return
            await asyncio.sleep(3)


async def run_concurrent_users(
    num_users: int,
    base_url: str,
    admin_email: str,
    admin_password: str,
    collector: MetricsCollector,
    stagger_delay: float = 1.0,
    think_time: tuple[float, float] = (0.5, 2.0),
):
    """Run multiple concurrent user journeys.

    Creates test users via the admin API, then runs them all concurrently.
    """
    print(f"\n  Preparing {num_users} concurrent user(s)...")

    # First, login as admin to create test users
    timeout = httpx.Timeout(connect=10, read=60, write=30, pool=10)
    async with httpx.AsyncClient(timeout=timeout) as admin_client:
        login_resp = await admin_client.post(
            f"{base_url}/api/auth/login",
            json={"email": admin_email, "password": admin_password},
        )
        if login_resp.status_code != 200:
            raise RuntimeError(
                f"Admin login failed ({login_resp.status_code}). "
                f"Check credentials: {admin_email}"
            )
        admin_token = login_resp.json()["access_token"]
        admin_client.headers["Authorization"] = f"Bearer {admin_token}"

        # Create test users
        users = []
        for i in range(num_users):
            email = f"loadtest_user{i+1}_{int(time.time())}@test.local"
            password = f"LoadTest{i+1}Secure!"
            username = f"loadtest_u{i+1}_{int(time.time())}"

            resp = await admin_client.post(
                f"{base_url}/api/admin/users",
                json={
                    "email": email,
                    "username": username,
                    "password": password,
                    "full_name": f"Load Test User {i+1}",
                    "role": "user",
                },
            )
            if resp.status_code == 201:
                users.append({"email": email, "password": password, "id": resp.json()["id"]})
                print(f"  Created test user: {email}")

                # Add user to a workspace
                ws_resp = await admin_client.get(f"{base_url}/api/workspaces")
                if ws_resp.status_code == 200:
                    workspaces = ws_resp.json()
                    if workspaces:
                        ws_id = workspaces[0]["id"]
                        await admin_client.post(
                            f"{base_url}/api/workspaces/{ws_id}/members",
                            json={"user_id": users[-1]["id"], "role": "editor"},
                        )
            elif resp.status_code == 409:
                # User exists, try with admin creds as fallback
                users.append({"email": admin_email, "password": admin_password})
                print(f"  User creation conflict, user {i+1} will use admin account")
            else:
                print(f"  Failed to create user {i+1}: {resp.status_code} {resp.text[:200]}")
                # Fallback to admin
                users.append({"email": admin_email, "password": admin_password})

    # If no users were created, use admin for all
    if not users:
        users = [{"email": admin_email, "password": admin_password}] * num_users

    # Start collecting
    collector.start()

    # Create and run user sessions
    tasks = []
    for i, user_creds in enumerate(users):
        session = UserSession(
            user_id=i + 1,
            base_url=base_url,
            email=user_creds["email"],
            password=user_creds["password"],
            collector=collector,
            think_time=think_time,
        )
        tasks.append(session.run_full_journey())

        # Stagger user starts to simulate realistic ramp-up
        if i < len(users) - 1:
            await asyncio.sleep(stagger_delay)

    # Wait for all users to complete
    await asyncio.gather(*tasks, return_exceptions=True)

    collector.stop()
