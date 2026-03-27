"""Celery tasks for document Q&A (background processing).

Implements a robust RAG pipeline with:
- Hybrid search (vector + keyword) for both semantic and exact matching
- Multi-query reformulation for better recall on factual/numerical questions
- Strict anti-hallucination prompts that force "not found" over guessing
"""
import asyncio
import json
import logging
import re
import uuid

from ..celery_app import celery
from ..services.progress_service import set_progress, get_progress

logger = logging.getLogger(__name__)

# Namespace for Q&A progress in Redis
NS = "document_qa"

# Timeout for vector_search sub-task calls (seconds).
_VECTOR_SEARCH_TIMEOUT = 120

CATEGORY_LABELS = {
    "old_rfp": "Ancien AO",
    "old_response": "Ancienne Reponse",
    "new_rfp": "Nouvel AO",
    "new_response": "Notre Reponse",
    "inspiration": "Inspiration",
}

# Regex to detect numerical/factual questions (percentages, amounts, etc.)
_NUMERICAL_QUERY_RE = re.compile(
    r'(?:taux|pourcentage|%|montant|chiffre|nombre|combien|quel.*est)'
    r'|(?:\d+[.,]?\d*\s*%)',
    re.IGNORECASE,
)


def _vector_search(project_id: str, query: str, top_k: int = 10,
                   category_filter: str | None = None,
                   document_ids: list[str] | None = None) -> list[dict]:
    """Run a vector search via the documents worker."""
    from celery.result import allow_join_result
    kwargs = {
        "project_id": project_id,
        "query": query,
        "top_k": top_k,
        "category_filter": category_filter,
    }
    if document_ids:
        kwargs["document_ids"] = document_ids
    result = celery.send_task("tasks.vector_search", kwargs=kwargs)
    with allow_join_result():
        return result.get(timeout=_VECTOR_SEARCH_TIMEOUT)


def _hybrid_search(project_id: str, query: str, top_k: int = 10,
                   category_filter: str | None = None,
                   document_ids: list[str] | None = None) -> list[dict]:
    """Run a hybrid search (vector + keyword) via the documents worker."""
    from celery.result import allow_join_result
    kwargs = {
        "project_id": project_id,
        "query": query,
        "top_k": top_k,
        "category_filter": category_filter,
    }
    if document_ids:
        kwargs["document_ids"] = document_ids
    result = celery.send_task("tasks.hybrid_search", kwargs=kwargs)
    with allow_join_result():
        try:
            return result.get(timeout=_VECTOR_SEARCH_TIMEOUT)
        except Exception:
            # Fallback to standard vector search if hybrid not registered yet
            logger.warning("Hybrid search failed, falling back to vector search")
            return _vector_search(project_id, query, top_k, category_filter, document_ids)


def _generate_search_queries(question: str) -> list[str]:
    """Generate multiple search queries to improve recall.

    For factual/numerical questions, reformulates the query in different
    ways to maximize the chance of finding the exact data point.
    """
    queries = [question]

    # For numerical questions, add keyword-focused variants
    if _NUMERICAL_QUERY_RE.search(question):
        # Extract key terms and create focused queries
        # Remove question words to get the core topic
        core = re.sub(
            r'(?:quel|quelle|quels|quelles|combien|est|sont|votre|le|la|les|des|du|de|en|et)\s+',
            ' ', question, flags=re.IGNORECASE,
        ).strip()
        if core and core != question:
            queries.append(core)

        # Add a percentage-focused variant
        if '%' in question or 'pourcentage' in question.lower() or 'taux' in question.lower():
            queries.append(f"{core} % pourcentage chiffre")

    return queries[:3]  # Max 3 queries


def _update(task_id: str, status: str, step: str, progress: int, message: str, **extra):
    data = {"status": status, "step": step, "progress": progress, "message": message}
    data.update(extra)
    set_progress(NS, task_id, data)


@celery.task(name="tasks.document_qa", bind=True, max_retries=0,
             soft_time_limit=180, time_limit=200)
def document_qa_task(
    self,
    task_id: str,
    project_id: str,
    workspace_id: str,
    question: str,
    document_ids: list[str] | None,
    categories: list[str] | None,
    include_generated_content: bool,
):
    """Celery wrapper for document Q&A."""
    asyncio.run(_run_document_qa(
        task_id,
        uuid.UUID(project_id),
        uuid.UUID(workspace_id),
        question,
        document_ids,
        categories,
        include_generated_content,
    ))


async def _run_document_qa(
    task_id: str,
    project_id: uuid.UUID,
    workspace_id: uuid.UUID,
    question: str,
    document_ids: list[str] | None,
    categories: list[str] | None,
    include_generated_content: bool,
):
    """Background task for document Q&A using RAG."""
    from sqlalchemy import select
    from collections import defaultdict
    from ..database import create_task_engine
    from ..models.project import RFPProject, AIConfig
    from ..models.chapter import Chapter
    from ..models.document import Document, DocumentImage
    from ..services.ai_service import create_ai_service, log_ai_usage_from_service

    _update(task_id, "running", "searching", 10, "Recherche dans les documents...")

    task_engine, TaskSession = create_task_engine()

    try:
        # ── Phase 1: Hybrid search (vector + keyword) with multi-query ──
        # Use hybrid search to find both semantically similar AND exact keyword matches.
        # Multi-query reformulates the question for better recall on factual data.
        is_numerical = bool(_NUMERICAL_QUERY_RE.search(question))
        search_queries = _generate_search_queries(question)
        base_top_k = 20 if is_numerical else 15  # More results for numerical questions

        all_search_results = []
        seen_chunk_ids = set()

        for sq in search_queries:
            if categories and not document_ids:
                for cat in categories:
                    cat_results = _hybrid_search(
                        str(project_id), sq, top_k=base_top_k, category_filter=cat,
                    )
                    for r in cat_results:
                        cid = r.get("chunk_id")
                        if cid not in seen_chunk_ids:
                            seen_chunk_ids.add(cid)
                            all_search_results.append(r)
            else:
                results = _hybrid_search(
                    str(project_id), sq, top_k=base_top_k * 2, document_ids=document_ids,
                )
                for r in results:
                    cid = r.get("chunk_id")
                    if cid not in seen_chunk_ids:
                        seen_chunk_ids.add(cid)
                        all_search_results.append(r)

        all_search_results.sort(key=lambda x: x.get("score", 0), reverse=True)

        # Adaptive threshold: lower for numerical queries (numbers may have low
        # semantic similarity but high keyword match)
        min_score = 0.15 if is_numerical else 0.3
        search_results = [r for r in all_search_results if r.get("score", 0) >= min_score]
        search_results = search_results[:30]  # Cap at 30 to avoid prompt bloat

        _update(task_id, "running", "context", 30, "Construction du contexte...")

        # ── Phase 2: Load additional context (DB session) ──
        async with TaskSession() as db:
            # Load AI config
            config_result = await db.execute(
                select(AIConfig).where(AIConfig.workspace_id == workspace_id)
            )
            config = config_result.scalar_one_or_none()
            ai_service = create_ai_service(config)

            # Load generated content if requested
            generated_context = ""
            if include_generated_content:
                ch_result = await db.execute(
                    select(Chapter)
                    .where(Chapter.project_id == project_id)
                    .where(Chapter.content != "")
                    .order_by(Chapter.order)
                )
                chapters = ch_result.scalars().all()
                if chapters:
                    ch_parts = []
                    for ch in chapters:
                        ch_parts.append(f"## {ch.title}\n{ch.content[:3000]}")
                    generated_context = "\n\n".join(ch_parts)

            if not search_results and not generated_context:
                has_filters = document_ids or categories
                if has_filters:
                    answer = "Je n'ai trouve aucune information pertinente dans les sources selectionnees pour repondre a cette question. Essayez de reformuler votre question ou de selectionner d'autres sources."
                else:
                    answer = "Je n'ai trouve aucun document pertinent pour repondre a cette question. Verifiez que des documents ont bien ete charges et traites dans le projet."
                _update(task_id, "completed", "done", 100, "Termine",
                        answer=answer, sources=[])
                return

            # Build context from search results — group by document
            doc_groups = defaultdict(list)
            for r in search_results:
                doc_key = r.get("document_name", "Document inconnu")
                doc_groups[doc_key].append(r)

            context_parts = []
            sources = []
            seen_sources = set()
            chunk_count = 0
            max_chunks = 20

            for doc_name, doc_results in doc_groups.items():
                doc_results.sort(key=lambda x: (x.get("page_number", 0), x.get("chunk_index", 0)))
                for r in doc_results:
                    if chunk_count >= max_chunks:
                        break
                    content = r["content"]
                    if content.startswith("passage: "):
                        content = content[9:]
                    category = r.get("category", "")
                    page = r.get("page_number", 0)
                    section = r.get("section_title", "")
                    cat_label = CATEGORY_LABELS.get(category, category)
                    score = r.get("score", 0)

                    header = f"[Source: {doc_name} | {cat_label} | page {page}"
                    if section:
                        header += f" | section: {section}"
                    header += f" | pertinence: {score:.0%}]"

                    context_parts.append(f"{header}\n{content}")
                    chunk_count += 1

                    source_key = f"{doc_name}|{page}"
                    if source_key not in seen_sources:
                        seen_sources.add(source_key)
                        sources.append({
                            "document_name": doc_name,
                            "category": category,
                            "category_label": cat_label,
                            "page_number": page,
                            "score": score,
                            "excerpt": content[:200],
                        })

            # Append generated content
            if generated_context:
                context_parts.append(
                    f"[Source: Contenu genere | Chapitres rediges | Reponse en cours]\n{generated_context}"
                )
                sources.append({
                    "document_name": "Contenu genere (chapitres)",
                    "category": "generated",
                    "category_label": "Contenu genere",
                    "page_number": 0,
                    "score": 1.0,
                    "excerpt": generated_context[:200],
                })

            # ── Load analyzed image metadata (OCR, descriptions, key info) ──
            image_query = (
                select(DocumentImage, Document.original_filename, Document.category)
                .join(Document, Document.id == DocumentImage.document_id)
                .where(Document.project_id == project_id)
                .where(Document.processing_status == "completed")
                .where(DocumentImage.analysis_status == "completed")
            )
            if document_ids:
                image_query = image_query.where(
                    Document.id.in_([uuid.UUID(d) for d in document_ids])
                )
            if categories:
                image_query = image_query.where(Document.category.in_(categories))

            image_result = await db.execute(image_query.order_by(DocumentImage.page_number))
            image_rows = image_result.all()

            image_context_parts = []
            for db_image, doc_name, doc_category in image_rows:
                img_type = db_image.image_type or ""
                if img_type in ("logo", "illustration") and not db_image.key_information:
                    continue

                description = db_image.anonymized_description or db_image.description or ""
                ocr_text = db_image.anonymized_ocr_text or db_image.ocr_text or ""
                key_info = db_image.key_information or []

                if not description and not ocr_text and not key_info:
                    continue

                cat_label = CATEGORY_LABELS.get(doc_category, doc_category or "")
                img_parts = [f"[Source image: {doc_name} | {cat_label} | page {db_image.page_number} | type: {img_type}]"]
                if description:
                    img_parts.append(f"Description: {description}")
                if key_info:
                    img_parts.append(f"Informations cles: {', '.join(str(k) for k in key_info)}")
                if ocr_text:
                    img_parts.append(f"Texte extrait (OCR): {ocr_text[:500]}")

                image_context_parts.append("\n".join(img_parts))

            if image_context_parts:
                image_context = "\n\n".join(image_context_parts[:10])
                context_parts.append(
                    f"[Donnees extraites des images analysees dans les documents]\n\n{image_context}"
                )
                sources.append({
                    "document_name": "Images analysees (OCR + Vision IA)",
                    "category": "images",
                    "category_label": "Analyse d'images",
                    "page_number": 0,
                    "score": 0.8,
                    "excerpt": image_context_parts[0][:200] if image_context_parts else "",
                })

            context_text = "\n\n---\n\n".join(context_parts)

            # Build document scope description
            doc_scope = ""
            if document_ids or categories:
                scope_parts = []
                if categories:
                    scope_parts.append(f"categories: {', '.join(categories)}")
                if document_ids:
                    doc_names_in_scope = list(doc_groups.keys())
                    scope_parts.append(f"documents: {', '.join(doc_names_in_scope)}")
                if include_generated_content:
                    scope_parts.append("contenu genere (chapitres rediges)")
                doc_scope = f"\n\nIMPORTANT: L'utilisateur a restreint la recherche aux sources suivantes : {'; '.join(scope_parts)}. Concentre ta reponse sur ces sources uniquement."
            elif include_generated_content:
                doc_scope = "\n\nIMPORTANT: L'utilisateur a demande d'inclure le contenu genere (chapitres rediges) dans la recherche. Utilise aussi ces informations pour repondre."

            system_prompt = f"""Tu es un assistant expert en analyse de documents pour les appels d'offres.
L'utilisateur te pose des questions sur les documents charges dans le projet.
Tu dois repondre en te basant UNIQUEMENT sur les extraits de documents fournis ci-dessous.

## REGLE NUMERO 1 — ZERO HALLUCINATION
- Tu ne dois JAMAIS inventer, deviner ou estimer un chiffre, un pourcentage, un montant, une date ou toute donnee factuelle.
- Si un chiffre ou une donnee precise n'apparait PAS textuellement dans les extraits fournis, tu DOIS repondre : **"Cette information n'apparait pas dans les extraits disponibles."**
- Tu ne dois JAMAIS utiliser tes connaissances generales ou parametriques pour completer une reponse. Tes SEULES sources sont les extraits ci-dessous.
- Il est ABSOLUMENT INTERDIT de produire un chiffre "vraisemblable" ou "typique du secteur" quand le chiffre exact n'est pas dans les extraits.
- En cas de doute entre deux valeurs trouvees dans les extraits, cite LES DEUX avec leurs sources respectives et laisse l'utilisateur trancher.

## REGLES DE REPONSE
- Base ta reponse EXCLUSIVEMENT sur les extraits fournis.
- Reponds de maniere precise, structuree et detaillee.
- Cite TOUJOURS tes sources avec le format exact : **(Source: nom_du_fichier.pdf, Categorie, page X)**
- Pour chaque affirmation factuelle, indique la source correspondante.
- Ne fais JAMAIS de supposition ou d'extrapolation au-dela de ce qui est ecrit dans les documents.
- Si l'information est partielle, indique-le et cite ce qui est disponible.
- Les extraits peuvent contenir des donnees issues de l'analyse d'images (descriptions, texte OCR, informations cles). Utilise ces informations au meme titre que le texte des documents. Cite la source image avec le format : **(Source image: nom_du_fichier.pdf, page X)**.

## TRAITEMENT DES QUESTIONS NUMERIQUES
Quand la question porte sur un chiffre, un pourcentage, un taux ou un montant :
1. Cherche d'abord le chiffre EXACT dans les extraits textuels.
2. Cherche ensuite dans les donnees extraites d'images (OCR, informations cles).
3. Si tu trouves le chiffre, cite-le EXACTEMENT comme il apparait dans la source, avec la reference precise.
4. Si tu ne trouves PAS le chiffre, reponds CLAIREMENT : "Le chiffre exact demande n'apparait pas dans les extraits fournis." Ne propose AUCUNE estimation.

Vocabulaire de categorie:
- "Ancien AO" = documents de categorie "Ancien AO" (ancien appel d'offres)
- "Ancienne Reponse" = documents de categorie "Ancienne Reponse"
- "Nouvel AO" / "cahier des charges" = documents de categorie "Nouvel AO"
- "Notre Reponse" = documents de categorie "Notre Reponse"
- "Inspiration" = documents d'inspiration / references
- "Contenu genere" = chapitres rediges par l'IA dans le cadre de la reponse en cours

Mise en forme:
- Utilise le markdown : titres (##), listes, **gras** pour les points cles.
- Si la question porte sur une comparaison, structure ta reponse en colonnes ou sections claires.
- Termine par une synthese courte si la reponse est longue.{doc_scope}"""

            user_prompt = f"""Voici les extraits pertinents des documents du projet (classes par document et page) :

{context_text}

---

Question de l'utilisateur : {question}

Reponds de maniere precise et structuree en citant systematiquement tes sources."""

            # ── Phase 3: LLM generation ──
            _update(task_id, "running", "generating", 60, "Generation de la reponse...")

            try:
                answer = await ai_service.generate_streaming(
                    system_prompt, user_prompt, temperature=0.2, timeout=120,
                )
            except Exception as e:
                logger.error("Document QA LLM failed for project %s: %s", project_id, e)
                _update(task_id, "error", "error", 0,
                        f"Erreur IA: {str(e)[:200]}")
                return

            # Log AI usage
            await log_ai_usage_from_service(db, project_id, "document_qa", ai_service)

        # ── Done ──
        _update(task_id, "completed", "done", 100, "Termine",
                answer=answer, sources=sources[:10])

    except Exception as e:
        logger.error("Document QA task failed: %s", e, exc_info=True)
        _update(task_id, "error", "error", 0, f"Erreur: {str(e)[:200]}")
    finally:
        await task_engine.dispose()
