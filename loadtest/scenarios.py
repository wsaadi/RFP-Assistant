"""Realistic user journey scenarios for load testing the RFP Assistant."""
import asyncio
import os
import time
import random
from typing import Optional

import httpx

from .metrics import MetricsCollector, RequestMetric, UserJourneyMetric, AIOperationMetric


class LiveDashboard:
    """Real-time dashboard showing concurrent user activity."""

    STEP_LABELS = {
        "login": "Login",
        "list_workspaces": "Workspaces",
        "create_project": "Create project",
        "upload_document": "Upload docs",
        "check_processing": "Processing",
        "search_documents": "Search",
        "generate_structure": "AI Structure",
        "structure_status": "AI Structure",
        "create_chapter": "Chapters",
        "create_sub_chapter": "Chapters",
        "generate_content": "AI Content",
        "chapter_gen_status": "AI Content",
        "compliance_analysis": "Compliance",
        "compliance_status": "Compliance",
        "export_word": "Export Word",
        "export_word_status": "Export Word",
        "download_word": "Export Word",
        "generate_soutenance": "Soutenance",
        "soutenance_status": "Soutenance",
        "delete_project": "Cleanup",
    }

    def __init__(self, num_users: int):
        self.num_users = num_users
        self.user_status: dict[int, str] = {}
        self.user_step: dict[int, str] = {}
        self.user_step_num: dict[int, int] = {}
        self.active_users = 0
        self.finished_users = 0
        self._header_printed = False
        self._last_line_count = 0

    def user_started(self, user_id: int):
        self.user_status[user_id] = "active"
        self.user_step[user_id] = "Starting..."
        self.user_step_num[user_id] = 0
        self.active_users += 1
        self._refresh()

    def user_progress(self, user_id: int, step: str, step_num: int, detail: str = ""):
        label = self.STEP_LABELS.get(step, step)
        if detail:
            label = f"{label}: {detail}"
        self.user_step[user_id] = label
        self.user_step_num[user_id] = step_num
        self._refresh()

    def user_finished(self, user_id: int, success: bool, error: str = ""):
        if success:
            self.user_status[user_id] = "done"
            self.user_step[user_id] = "DONE (12/12)"
        else:
            self.user_status[user_id] = "fail"
            self.user_step[user_id] = f"FAILED: {error[:40]}" if error else "FAILED"
        self.active_users = max(0, self.active_users - 1)
        self.finished_users += 1
        self._refresh()

    def _refresh(self):
        """Redraw the dashboard."""
        import sys

        # Clear previous lines
        if self._last_line_count > 0:
            sys.stdout.write(f"\033[{self._last_line_count}A\033[J")

        lines = []
        lines.append(f"  Active: {self.active_users}/{self.num_users}  |  "
                      f"Finished: {self.finished_users}/{self.num_users}")
        lines.append(f"  {'─' * 68}")

        for uid in sorted(self.user_status.keys()):
            status = self.user_status[uid]
            step = self.user_step[uid]
            step_num = self.user_step_num[uid]

            if status == "active":
                bar = self._progress_bar(step_num, 12)
                icon = ">>>"
            elif status == "done":
                bar = self._progress_bar(12, 12)
                icon = "[OK]"
            else:
                bar = self._progress_bar(step_num, 12)
                icon = "[!!]"

            lines.append(f"  {icon} User {uid:<3d} {bar}  {step}")

        lines.append("")

        output = "\n".join(lines)
        sys.stdout.write(output + "\n")
        sys.stdout.flush()
        self._last_line_count = len(lines)

    @staticmethod
    def _progress_bar(current: int, total: int, width: int = 16) -> str:
        filled = int(width * current / total) if total > 0 else 0
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {current:>2d}/{total}"

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
        dashboard: Optional[LiveDashboard] = None,
    ):
        self.user_id = user_id
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.collector = collector
        self.think_time = think_time
        self.dashboard = dashboard

        self.client: Optional[httpx.AsyncClient] = None
        self.token: Optional[str] = None
        self.workspace_id: Optional[str] = None
        self.project_id: Optional[str] = None
        self.chapter_ids: list[str] = []
        self.document_ids: list[str] = []

    def _report(self, step: str, step_num: int, detail: str = ""):
        """Report progress to the live dashboard."""
        if self.dashboard:
            self.dashboard.user_progress(self.user_id, step, step_num, detail)

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

        if self.dashboard:
            self.dashboard.user_started(self.user_id)

        timeout = httpx.Timeout(connect=10, read=300, write=30, pool=10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            self.client = client
            try:
                # Step 1: Login
                self._report("login", 0)
                await self._step_login()
                journey.steps_completed += 1
                await self._think()

                # Step 2: List workspaces
                self._report("list_workspaces", 1)
                await self._step_list_workspaces()
                journey.steps_completed += 1
                await self._think()

                # Step 3: Create project
                self._report("create_project", 2)
                await self._step_create_project()
                journey.steps_completed += 1
                await self._think()

                # Step 4: Upload documents (RFP + old response)
                self._report("upload_document", 3)
                await self._step_upload_documents()
                journey.steps_completed += 1
                await self._think()

                # Step 5: Wait for document processing
                self._report("check_processing", 4)
                await self._step_wait_processing()
                journey.steps_completed += 1
                await self._think()

                # Step 6: Search documents
                self._report("search_documents", 5)
                await self._step_search_documents()
                journey.steps_completed += 1
                await self._think()

                # Step 7: Generate chapter structure (AI call)
                self._report("generate_structure", 6)
                await self._step_generate_structure()
                journey.steps_completed += 1
                await self._think()

                # Step 8: Create chapters manually
                self._report("create_chapter", 7)
                await self._step_create_chapters()
                journey.steps_completed += 1
                await self._think()

                # Step 9: Generate chapter content (AI call)
                self._report("generate_content", 8)
                await self._step_generate_content()
                journey.steps_completed += 1
                await self._think()

                # Step 10: Run compliance analysis (AI call)
                self._report("compliance_analysis", 9)
                await self._step_compliance_analysis()
                journey.steps_completed += 1
                await self._think()

                # Step 11: Export Word document
                self._report("export_word", 10)
                await self._step_export_word()
                journey.steps_completed += 1
                await self._think()

                # Step 12: Generate soutenance (AI call)
                self._report("generate_soutenance", 11)
                await self._step_generate_soutenance()
                journey.steps_completed += 1

                # Cleanup: delete project
                self._report("delete_project", 12)
                await self._step_cleanup()

                journey.success = True

            except Exception as e:
                journey.error = str(e)
                journey.success = False

            finally:
                journey.finished_at = time.time()
                self.collector.record_journey(journey)
                if self.dashboard:
                    self.dashboard.user_finished(
                        self.user_id, journey.success, journey.error or ""
                    )
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
        else:
            raise RuntimeError(f"Login failed: {resp.status_code if resp else 'no response'}")

    async def _step_list_workspaces(self):
        """List workspaces and pick the first one."""
        resp, _ = await self._request("list_workspaces", "GET", "/api/workspaces")
        if resp and resp.status_code == 200:
            workspaces = resp.json()
            if workspaces:
                self.workspace_id = workspaces[0]["id"]
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
            self._report("create_project", 2, project_name)
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
                self._report("upload_document", 3, f"skip {filename}")
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
                self._report("upload_document", 3, f"{filename}")
            else:
                status = resp.status_code if resp else "no response"
                self._report("upload_document", 3, f"FAIL {filename}: {status}")

            await self._think()

    async def _step_wait_processing(self):
        """Poll document processing progress until complete or timeout."""
        ai_op = AIOperationMetric(
            user_id=self.user_id,
            operation="document_processing",
            started_at=time.monotonic(),
        )
        max_wait = 180  # seconds
        poll_interval = 3
        start = time.monotonic()
        poll_count = 0
        final_status = "timeout"

        while (time.monotonic() - start) < max_wait:
            resp, _ = await self._request(
                "check_processing", "GET",
                f"/api/documents/progress/{self.project_id}",
            )
            poll_count += 1
            if resp and resp.status_code == 200:
                progress = resp.json().get("progress", [])
                if not progress:
                    final_status = "completed"
                    self._report("check_processing", 4, "done")
                    break
                all_done = all(
                    p.get("db_status") in ("completed", "failed") or p.get("progress", 0) == 100
                    for p in progress
                )
                if all_done:
                    any_failed = any(p.get("db_status") == "failed" for p in progress)
                    final_status = "completed" if not any_failed else "partial"
                    self._report("check_processing", 4, "done")
                    break

            await asyncio.sleep(poll_interval)

        if final_status == "timeout":
            self._report("check_processing", 4, "timeout")
        ai_op.finish(final_status, poll_count)
        self.collector.record_ai_operation(ai_op)

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
                self._report("search_documents", 5, f"'{query}' -> {len(results)}")
            await self._think()

    async def _step_generate_structure(self):
        """Trigger AI-based chapter structure generation."""
        ai_op = AIOperationMetric(
            user_id=self.user_id,
            operation="generate_structure",
            started_at=time.monotonic(),
        )
        resp, _ = await self._request(
            "generate_structure", "POST",
            f"/api/projects/{self.project_id}/generate-structure",
            json={},
        )
        if resp and resp.status_code == 200:
            self._report("generate_structure", 6, "polling...")
            final_status, polls = await self._poll_progress(
                "structure_status", f"/api/projects/{self.project_id}/generation-status"
            )
            ai_op.finish(final_status, polls)
            self._report("structure_status", 6, f"{final_status} ({ai_op.duration_s}s)")
        else:
            status = resp.status_code if resp else "no response"
            ai_op.finish("error")
            self._report("generate_structure", 6, f"HTTP {status}")
        self.collector.record_ai_operation(ai_op)

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
                self._report("create_chapter", 7, tmpl["title"])

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
        """Trigger AI content generation for chapters (in parallel)."""
        if not self.chapter_ids:
            self._report("generate_content", 8, "no chapters")
            return

        # Generate content for up to 2 chapters — fire all at once, poll in parallel
        chapters_to_gen = self.chapter_ids[:2]

        async def _gen_one(chapter_id: str):
            ai_op = AIOperationMetric(
                user_id=self.user_id,
                operation="generate_content",
                started_at=time.monotonic(),
            )
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
                self._report("generate_content", 8, "polling...")
                final_status, polls = await self._poll_chapter_gen(chapter_id)
                ai_op.finish(final_status, polls)
                self._report("chapter_gen_status", 8, f"{final_status} ({ai_op.duration_s}s)")
            else:
                status = resp.status_code if resp else "no response"
                ai_op.finish("error")
                self._report("generate_content", 8, f"HTTP {status}")
            self.collector.record_ai_operation(ai_op)

        # Launch all chapter generations concurrently
        await asyncio.gather(*[_gen_one(cid) for cid in chapters_to_gen])

    async def _step_compliance_analysis(self):
        """Run compliance analysis (AI-powered)."""
        ai_op = AIOperationMetric(
            user_id=self.user_id,
            operation="compliance_analysis",
            started_at=time.monotonic(),
        )
        resp, _ = await self._request(
            "compliance_analysis", "POST",
            f"/api/projects/{self.project_id}/compliance-analysis",
            json={},
        )
        if resp:
            if resp.status_code == 200:
                self._report("compliance_analysis", 9, "polling...")
                final_status, polls = await self._poll_progress(
                    "compliance_status",
                    f"/api/projects/{self.project_id}/compliance-analysis-status",
                )
                ai_op.finish(final_status, polls)
                self._report("compliance_status", 9, f"{final_status} ({ai_op.duration_s}s)")
            else:
                ai_op.finish("error")
                self._report("compliance_analysis", 9, f"HTTP {resp.status_code}")
        else:
            ai_op.finish("error")
            self._report("compliance_analysis", 9, "no response")
        self.collector.record_ai_operation(ai_op)

    async def _step_export_word(self):
        """Export project as Word document."""
        ai_op = AIOperationMetric(
            user_id=self.user_id,
            operation="export_word",
            started_at=time.monotonic(),
        )
        resp, _ = await self._request(
            "export_word", "POST",
            f"/api/export/{self.project_id}/word",
            json={},
        )
        if resp and resp.status_code == 200:
            self._report("export_word", 10, "polling...")
            max_wait = 180
            start = time.monotonic()
            poll_count = 0
            final_status = "timeout"
            while (time.monotonic() - start) < max_wait:
                status_resp, _ = await self._request(
                    "export_word_status", "GET",
                    f"/api/export/{self.project_id}/word-status",
                )
                poll_count += 1
                if status_resp and status_resp.status_code == 200:
                    data = status_resp.json()
                    if data.get("status") in ("completed", "ready"):
                        final_status = "completed"
                        self._report("export_word", 10, "downloading")
                        await self._request(
                            "download_word", "GET",
                            f"/api/export/{self.project_id}/word-download",
                        )
                        break
                    elif data.get("status") == "failed":
                        final_status = "failed"
                        self._report("export_word", 10, "failed")
                        break
                await asyncio.sleep(3)
            ai_op.finish(final_status, poll_count)
        else:
            status = resp.status_code if resp else "no response"
            ai_op.finish("error")
            self._report("export_word", 10, f"HTTP {status}")
        self.collector.record_ai_operation(ai_op)

    async def _step_generate_soutenance(self):
        """Generate soutenance/defense materials (AI-powered)."""
        ai_op = AIOperationMetric(
            user_id=self.user_id,
            operation="generate_soutenance",
            started_at=time.monotonic(),
        )
        resp, _ = await self._request(
            "generate_soutenance", "POST",
            f"/api/export/{self.project_id}/soutenance",
            json={},
        )
        if resp:
            if resp.status_code == 200:
                self._report("generate_soutenance", 11, "polling...")
                max_wait = 180
                start = time.monotonic()
                poll_count = 0
                final_status = "timeout"
                while (time.monotonic() - start) < max_wait:
                    status_resp, _ = await self._request(
                        "soutenance_status", "GET",
                        f"/api/export/{self.project_id}/soutenance-status",
                    )
                    poll_count += 1
                    if status_resp and status_resp.status_code == 200:
                        data = status_resp.json()
                        if data.get("status") in ("completed", "ready", "idle"):
                            final_status = data.get("status", "completed")
                            self._report("soutenance_status", 11, f"{final_status} ({ai_op.duration_s}s)")
                            break
                        elif data.get("status") == "failed":
                            final_status = "failed"
                            self._report("soutenance_status", 11, "failed")
                            break
                    await asyncio.sleep(3)
                ai_op.finish(final_status, poll_count)
            else:
                ai_op.finish("error")
                self._report("generate_soutenance", 11, f"HTTP {resp.status_code}")
        else:
            ai_op.finish("error")
        self.collector.record_ai_operation(ai_op)

    async def _step_cleanup(self):
        """Delete the test project to clean up."""
        if self.project_id:
            resp, _ = await self._request(
                "delete_project", "DELETE",
                f"/api/projects/{self.project_id}",
            )

    async def _poll_progress(self, step_name: str, status_url: str, max_wait: int = 180) -> tuple[str, int]:
        """Generic progress polling. Returns (final_status, poll_count)."""
        poll_count = 0
        start = time.monotonic()
        while (time.monotonic() - start) < max_wait:
            resp, _ = await self._request(step_name, "GET", status_url)
            poll_count += 1
            if resp and resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "")
                if status in ("completed", "ready", "idle"):
                    return status, poll_count
                if status == "failed":
                    return "failed", poll_count
            await asyncio.sleep(3)
        return "timeout", poll_count

    async def _poll_chapter_gen(self, chapter_id: str, max_wait: int = 180) -> tuple[str, int]:
        """Poll chapter generation status. Returns (final_status, poll_count)."""
        poll_count = 0
        start = time.monotonic()
        while (time.monotonic() - start) < max_wait:
            resp, _ = await self._request(
                "chapter_gen_status", "GET",
                f"/api/chapters/{chapter_id}/generate-status",
            )
            poll_count += 1
            if resp and resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "")
                if status in ("completed", "idle"):
                    return status, poll_count
                if status == "failed":
                    return "failed", poll_count
            await asyncio.sleep(3)
        return "timeout", poll_count


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
    Each user starts immediately as a real asyncio task with staggered delays.
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

    # ── Validate AI provider configuration ──
    # Check the workspace AI config to warn if providers are set to local
    # Ollama (which processes requests sequentially and will bottleneck
    # concurrent users). Cloud providers (Mistral, Scaleway) handle
    # parallel requests properly.
    try:
        ws_resp = await admin_client.get(f"{base_url}/api/workspaces")
        if ws_resp.status_code == 200:
            workspaces = ws_resp.json()
            if workspaces:
                ws_id = workspaces[0]["id"]
                cfg_resp = await admin_client.get(
                    f"{base_url}/api/admin/ai-config/{ws_id}"
                )
                if cfg_resp.status_code == 200:
                    cfg = cfg_resp.json()
                    llm_provider = cfg.get("provider", "mistral")
                    ner_provider = cfg.get("ner_provider", "ollama")
                    vision_provider = cfg.get("vision_provider", "ollama")
                    print(f"\n  AI Config (workspace {ws_id[:8]}...):")
                    print(f"    LLM provider:    {llm_provider} ({cfg.get('model_name', '?')})")
                    print(f"    NER provider:    {ner_provider} ({cfg.get('ner_model', '?')})")
                    print(f"    Vision provider: {vision_provider} ({cfg.get('vision_model', '?')})")

                    warnings = []
                    if llm_provider == "ollama":
                        warnings.append("LLM")
                    if ner_provider == "ollama":
                        warnings.append("NER/anonymization")
                    if vision_provider == "ollama":
                        warnings.append("Vision/image analysis")

                    if warnings and num_users > 1:
                        print(f"\n  WARNING: {', '.join(warnings)} using Ollama (local).")
                        print(f"  Ollama processes requests sequentially — {num_users} concurrent")
                        print(f"  users WILL experience queuing delays and potential timeouts.")
                        print(f"  For load testing, configure cloud providers (Mistral/Scaleway)")
                        print(f"  via the admin UI or PUT /api/admin/ai-config/{{workspace_id}}")
                    elif not warnings:
                        print(f"    All providers are cloud-based — good for {num_users} concurrent users")
                else:
                    print(f"\n  Could not read AI config (HTTP {cfg_resp.status_code}), skipping validation")
    except Exception as e:
        print(f"\n  Could not validate AI config: {e}")

    # Live dashboard
    dashboard = LiveDashboard(num_users)

    # Start collecting
    collector.start()

    print(f"\n  Launching {num_users} user(s) with {stagger_delay}s stagger...\n")

    # Launch user sessions as real asyncio tasks for true concurrency
    tasks: list[asyncio.Task] = []
    for i, user_creds in enumerate(users):
        session = UserSession(
            user_id=i + 1,
            base_url=base_url,
            email=user_creds["email"],
            password=user_creds["password"],
            collector=collector,
            think_time=think_time,
            dashboard=dashboard,
        )
        # create_task starts the coroutine IMMEDIATELY on the event loop
        task = asyncio.create_task(session.run_full_journey())
        tasks.append(task)

        # Stagger: wait before launching the NEXT user (previous one is already running)
        if i < len(users) - 1:
            await asyncio.sleep(stagger_delay)

    # Wait for all running tasks to complete
    await asyncio.gather(*tasks, return_exceptions=True)

    collector.stop()
