"""AI service for Mistral API integration."""
import asyncio
import json
import logging
import re
from typing import Awaitable, Callable, List, Optional, Dict

from mistralai import Mistral

from ..models.project import AIConfig

logger = logging.getLogger(__name__)


# ── Robust JSON parsing helpers ──────────────────────────────────────

def _clean_json_response(raw: str) -> str:
    """Strip markdown fences, leading/trailing prose around JSON."""
    text = raw.strip()
    # Remove ```json ... ``` or ``` ... ``` wrappers
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)
    return text.strip()


def _repair_truncated_json(text: str, target: str = "array") -> str:
    """Attempt to close unclosed brackets/braces in truncated JSON.

    LLMs sometimes hit max_tokens and produce truncated JSON like:
        [{"title": "A", "children": [{"title": "B"
    Uses a stack-based approach to close structures in the correct
    nesting order (e.g. }]}] not }}]]).
    """
    text = text.rstrip()

    # Step 1: Detect if we're inside an unclosed string and close it
    in_string = False
    escape = False
    for c in text:
        if escape:
            escape = False
            continue
        if c == '\\' and in_string:
            escape = True
            continue
        if c == '"':
            in_string = not in_string
    if in_string:
        text += '"'

    # Step 2: Remove trailing comma or colon (incomplete key-value pair)
    text = re.sub(r'[,:]\s*$', '', text)

    # Step 3: Track nesting with a stack to know what to close
    stack: list[str] = []
    in_string = False
    escape = False
    for c in text:
        if escape:
            escape = False
            continue
        if c == '\\' and in_string:
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c in ('{', '['):
            stack.append(c)
        elif c == '}' and stack and stack[-1] == '{':
            stack.pop()
        elif c == ']' and stack and stack[-1] == '[':
            stack.pop()

    # Step 4: Close in reverse nesting order
    closing = []
    for opener in reversed(stack):
        closing.append('}' if opener == '{' else ']')

    return text + ''.join(closing)


def _parse_json_array(raw: str) -> Optional[List]:
    """Try to parse a JSON array from a raw LLM response, with repair."""
    cleaned = _clean_json_response(raw)

    # 1. Try direct parse of the full cleaned text
    if cleaned.startswith('['):
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # 2. Try regex extraction
    match = re.search(r'\[[\s\S]*\]', cleaned)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # 3. Try to repair truncated JSON (find the opening [ and close it)
    idx = cleaned.find('[')
    if idx >= 0:
        fragment = cleaned[idx:]
        repaired = _repair_truncated_json(fragment, target="array")
        try:
            result = json.loads(repaired)
            logger.warning("JSON was truncated — repaired by closing %d brackets/braces",
                          repaired.count(']') + repaired.count('}') - fragment.count(']') - fragment.count('}'))
            return result
        except json.JSONDecodeError:
            pass

    return None


def _parse_json_object(raw: str) -> Optional[Dict]:
    """Try to parse a JSON object from a raw LLM response, with repair."""
    cleaned = _clean_json_response(raw)

    # 1. Try direct parse
    if cleaned.startswith('{'):
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # 2. Try regex extraction
    match = re.search(r'\{[\s\S]*\}', cleaned)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # 3. Try to repair truncated JSON
    idx = cleaned.find('{')
    if idx >= 0:
        fragment = cleaned[idx:]
        repaired = _repair_truncated_json(fragment, target="object")
        try:
            result = json.loads(repaired)
            logger.warning("JSON object was truncated — repaired")
            return result
        except json.JSONDecodeError:
            pass

    return None


class MistralAIService:
    """Service for AI-powered operations using Mistral API."""

    def __init__(self, api_key: str, model: str = "mistral-large-latest",
                 temperature: float = 0.3, max_tokens: int = 4096):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = Mistral(api_key=api_key)

    @classmethod
    def from_config(cls, config: AIConfig, decrypted_key: str) -> "MistralAIService":
        return cls(
            api_key=decrypted_key,
            model=config.model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    async def generate(
        self, system_prompt: str, user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: float = 300,
    ) -> str:
        """Generate text using Mistral API (reuses client connection).

        Args:
            timeout: Maximum seconds to wait for the API response (default 5 min).
        """
        input_chars = len(system_prompt) + len(user_prompt)
        effective_max = max_tokens or self.max_tokens
        logger.info("Mistral call: ~%d input chars (~%d tokens), max_output=%d, model=%s",
                     input_chars, input_chars // 4, effective_max, self.model)

        coro = self._client.chat.complete_async(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature or self.temperature,
            max_tokens=effective_max,
        )
        try:
            response = await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.error("Mistral call timed out after %.0fs (input ~%d chars)", timeout, input_chars)
            raise TimeoutError(f"L'appel IA a expire apres {timeout:.0f}s. Essayez avec des documents plus courts.")

        result = response.choices[0].message.content or ""
        logger.info("Mistral response: %d chars (~%d tokens)", len(result), len(result) // 4)
        return result

    async def generate_streaming(
        self, system_prompt: str, user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: float = 600,
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> str:
        """Generate text using Mistral streaming API.

        Streams tokens one by one. Calls ``on_progress(tokens_received, chars_received)``
        every ~50 tokens so the caller can update a progress indicator with real data.

        Args:
            on_progress: async callback(token_count, char_count) called periodically.
            timeout: Hard wall-clock timeout for the entire stream (default 10 min).
        """
        import time

        input_chars = len(system_prompt) + len(user_prompt)
        effective_max = max_tokens or self.max_tokens
        logger.info("Mistral STREAM call: ~%d input chars (~%d tokens), max_output=%d, model=%s",
                     input_chars, input_chars // 4, effective_max, self.model)

        t0 = time.monotonic()
        chunks: list[str] = []
        token_count = 0

        try:
            stream = await asyncio.wait_for(
                self._client.chat.stream_async(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature or self.temperature,
                    max_tokens=effective_max,
                ),
                timeout=60,  # 60s to *start* the stream
            )

            async with stream as event_stream:
                async for event in event_stream:
                    # Wall-clock guard
                    if time.monotonic() - t0 > timeout:
                        logger.error("Streaming timed out after %.0fs", timeout)
                        raise TimeoutError(f"L'appel IA a expire apres {timeout:.0f}s.")

                    chunk = event.data
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        content = getattr(delta, "content", None)
                        if content is not None and content:
                            # content may be str or list of TextChunk/ThinkChunk
                            if isinstance(content, str):
                                text = content
                            elif isinstance(content, list):
                                text = "".join(
                                    getattr(part, "text", "") for part in content
                                )
                            else:
                                text = str(content)

                            if text:
                                chunks.append(text)
                                token_count += 1

                                if on_progress and token_count % 50 == 0:
                                    total_chars = sum(len(c) for c in chunks)
                                    await on_progress(token_count, total_chars)

        except asyncio.TimeoutError:
            logger.error("Mistral stream init timed out after 60s (input ~%d chars)", input_chars)
            raise TimeoutError("L'appel IA a expire en attendant le debut du stream.")

        result = "".join(chunks)
        elapsed = time.monotonic() - t0
        logger.info("Mistral stream done: %d tokens, %d chars in %.1fs (%.0f tok/s)",
                     token_count, len(result), elapsed,
                     token_count / elapsed if elapsed > 0 else 0)
        return result

    async def test_connection(self) -> str:
        """Test the API connection."""
        return await self.generate(
            "Tu es un assistant utile.",
            "Réponds simplement 'Connexion Mistral réussie'.",
            temperature=0.1,
        )

    async def analyze_gap(
        self, old_rfp_content: str, new_rfp_content: str,
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> Dict:
        """Analyze differences between old and new RFP."""
        system_prompt = """Tu es un expert en analyse d'appels d'offres.
Tu dois comparer un ancien appel d'offres avec un nouveau pour identifier les écarts.

Analyse minutieusement les deux documents et identifie:
1. Les exigences nouvelles dans le nouvel AO
2. Les exigences supprimées de l'ancien AO
3. Les exigences modifiées
4. Les exigences inchangées

Réponds EXACTEMENT au format JSON suivant (sans markdown):
{
  "new_requirements": [{"title": "...", "description": "...", "priority": "high|medium|low"}],
  "removed_requirements": [{"title": "...", "description": "..."}],
  "modified_requirements": [{"title": "...", "old_description": "...", "new_description": "...", "impact": "..."}],
  "unchanged_requirements": [{"title": "...", "description": "..."}],
  "summary": "..."
}"""

        user_prompt = f"""ANCIEN APPEL D'OFFRES:
{old_rfp_content[:50000]}

NOUVEL APPEL D'OFFRES:
{new_rfp_content[:50000]}

Analyse les écarts entre ces deux appels d'offres."""

        response = await self.generate_streaming(
            system_prompt, user_prompt, temperature=0.2, max_tokens=12000,
            timeout=600, on_progress=on_progress,
        )
        result = _parse_json_object(response)
        if result:
            return result
        logger.warning("Gap analysis: JSON parse failed. Raw response (first 500 chars): %s", response[:500])
        return {"summary": response[:2000], "new_requirements": [], "removed_requirements": [],
                "modified_requirements": [], "unchanged_requirements": []}

    async def generate_response_structure(
        self,
        new_rfp_content: str,
        old_rfp_content: str = "",
        old_response_content: str = "",
        gap_analysis: Optional[Dict] = None,
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> List[Dict]:
        """Generate the complete response structure by deeply analyzing the new RFP,
        comparing with the old RFP, and leveraging the old response."""
        system_prompt = """Tu es un expert senior en réponse aux appels d'offres avec 20 ans d'expérience.

Ta mission est de créer la STRUCTURE IDÉALE et COMPLÈTE de la réponse au nouvel appel d'offres.

## Ta méthodologie:
1. ANALYSE EXHAUSTIVE du nouvel AO: identifie TOUTES les exigences, critères, lots, livrables demandés
2. COMPARAISON avec l'ancien AO: identifie ce qui a changé, ce qui est nouveau, ce qui a disparu
3. CAPITALISATION sur l'ancienne réponse: reprends la structure qui fonctionnait et adapte-la
4. CONSTRUCTION du chapitrage idéal: crée une structure qui couvre 100% des exigences du nouvel AO

## Règles pour la structure:
- Chaque exigence du nouvel AO DOIT être couverte par au moins un chapitre/sous-chapitre
- Les chapitres suivent l'ordre logique attendu par l'acheteur (souvent celui du RC/CCTP)
- Inclure les chapitres administratifs (présentation société, références, moyens, etc.)
- Inclure les annexes et documents à fournir mentionnés dans l'AO
- Les descriptions doivent être précises et indiquer clairement le contenu attendu
- Le champ rfp_requirement doit citer EXACTEMENT l'exigence de l'AO concernée
- Le champ delta indique si c'est une exigence nouvelle, modifiée, ou inchangée par rapport à l'ancien AO

Réponds UNIQUEMENT au format JSON suivant (sans markdown, sans commentaire):
[
  {
    "title": "Titre du chapitre",
    "description": "Description détaillée du contenu attendu dans ce chapitre",
    "chapter_type": "chapter",
    "rfp_requirement": "Citation exacte ou résumé de l'exigence du nouvel AO",
    "delta": "new|modified|unchanged|removed_context",
    "children": [
      {
        "title": "Titre du sous-chapitre",
        "description": "Description détaillée",
        "chapter_type": "sub_chapter",
        "rfp_requirement": "Exigence spécifique",
        "delta": "new|modified|unchanged",
        "children": []
      }
    ]
  }
]

Valeurs de delta:
- "new": exigence absente de l'ancien AO
- "modified": exigence existante mais modifiée
- "unchanged": exigence identique à l'ancien AO
- "removed_context": chapitre nécessaire même si l'exigence directe a été retirée (contexte, transition)"""

        # Mistral Large supports 128K context.
        # Priority: maximize coverage of the new RFP, then old response, then old RFP.
        # Total budget: ~80K + 40K + 40K = 160K chars ≈ 40-50K tokens (fits in 128K context).
        parts = []

        parts.append(f"CONTENU DU NOUVEL APPEL D'OFFRES:\n{new_rfp_content[:80000]}")

        if old_rfp_content:
            parts.append(f"CONTENU DE L'ANCIEN APPEL D'OFFRES:\n{old_rfp_content[:40000]}")

        if old_response_content:
            parts.append(f"CONTENU DE L'ANCIENNE RÉPONSE (structure et texte):\n{old_response_content[:40000]}")

        if gap_analysis:
            gap_summary = []
            if gap_analysis.get("summary"):
                gap_summary.append(f"  Résumé: {gap_analysis['summary']}")
            for req in gap_analysis.get("new_requirements", []):
                gap_summary.append(f"  [NOUVEAU] {req.get('title', '')}: {req.get('description', '')}")
            for req in gap_analysis.get("modified_requirements", []):
                gap_summary.append(f"  [MODIFIÉ] {req.get('title', '')}: {req.get('new_description', '')}")
            for req in gap_analysis.get("removed_requirements", []):
                gap_summary.append(f"  [SUPPRIMÉ] {req.get('title', '')}: {req.get('description', '')}")
            for req in gap_analysis.get("unchanged_requirements", []):
                gap_summary.append(f"  [INCHANGÉ] {req.get('title', '')}")
            if gap_summary:
                parts.append(f"ANALYSE DES ÉCARTS ANCIEN/NOUVEAU AO:\n" + "\n".join(gap_summary))

        user_prompt = "\n\n---\n\n".join(parts)
        user_prompt += "\n\nAnalyse en profondeur le nouvel AO et génère la structure complète et idéale de la réponse."

        # First attempt
        response = await self.generate_streaming(
            system_prompt, user_prompt, temperature=0.2, max_tokens=12000,
            timeout=600, on_progress=on_progress,
        )
        result = _parse_json_array(response)
        if result:
            return result

        # Log the failure for diagnostics
        logger.warning("Structure gen: JSON parse failed on first attempt. "
                       "Response length: %d chars. First 500 chars: %s",
                       len(response), response[:500])
        logger.warning("Structure gen: Last 300 chars: %s", response[-300:])

        # Retry once with a more explicit prompt asking for valid JSON
        logger.info("Structure gen: retrying with explicit JSON instruction...")
        retry_prompt = (
            user_prompt
            + "\n\nIMPORTANT: Ta réponse précédente n'était pas du JSON valide. "
            "Réponds UNIQUEMENT avec le tableau JSON, sans texte avant ni après, "
            "sans balises markdown. Commence directement par [ et termine par ]."
        )
        response2 = await self.generate_streaming(
            system_prompt, retry_prompt, temperature=0.1, max_tokens=12000,
            timeout=600, on_progress=on_progress,
        )
        result2 = _parse_json_array(response2)
        if result2:
            logger.info("Structure gen: retry succeeded with %d chapters", len(result2))
            return result2

        logger.error("Structure gen: JSON parse failed on retry too. "
                     "Response length: %d chars. First 500: %s",
                     len(response2), response2[:500])
        return []

    async def detect_deliverables(
        self,
        new_rfp_content: str,
        old_response_content: str = "",
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> List[Dict]:
        """Analyze the RFP to detect all expected deliverables/documents."""
        system_prompt = """Tu es un expert senior en marchés publics et appels d'offres.

Ta mission est d'analyser le contenu d'un appel d'offres pour identifier TOUS les documents
et livrables que le candidat doit fournir dans sa réponse.

## Ce que tu dois identifier:
- Le mémoire technique (ou offre technique)
- L'acte d'engagement (AE)
- Le bordereau des prix unitaires (BPU)
- Le détail quantitatif estimatif (DQE) ou DPGF
- Les annexes spécifiques demandées (annexes techniques, financières, etc.)
- Les formulaires obligatoires (DC1, DC2, ATTRI1, etc.)
- Les attestations et certificats demandés
- Le planning ou calendrier d'exécution
- Les fiches de références / expériences similaires
- Les CV des intervenants clés
- Le mémoire environnemental / RSE si demandé
- Tout autre document spécifiquement mentionné dans le RC, le CCTP ou le CCP

## Règles:
- Base-toi UNIQUEMENT sur ce que l'AO demande explicitement
- Cite la source dans l'AO (article, page, section) quand possible
- Indique le format attendu (docx, xlsx, pdf) si précisé dans l'AO
- Classe les documents par ordre logique de présentation
- Si une ancienne réponse est fournie, utilise-la pour confirmer/compléter la liste

## IMPORTANT - Classification du type de contenu (content_type):
Tu DOIS classifier chaque livrable selon son type de contenu:

- "redaction": Document à RÉDIGER entièrement par le candidat (mémoire technique, note méthodologique, planning détaillé rédigé, etc.)
  → Le candidat écrit le contenu de zéro, avec des chapitres et du texte libre.

- "completion": Document FOURNI par l'acheteur que le candidat doit COMPLÉTER/REMPLIR (BPU Excel, DQE, DPGF, formulaires DC1/DC2, AE pré-formaté, cadre de réponse imposé, etc.)
  → Le candidat remplit des cases, cellules, champs dans un document existant fourni par le client.

Indices pour "completion":
- BPU, DQE, DPGF → toujours "completion" (tableurs à compléter)
- Formulaires administratifs (DC1, DC2, ATTRI1, NOTI1) → "completion"
- Acte d'engagement pré-formaté → "completion"
- Cadre de réponse technique imposé par l'acheteur → "completion"
- Document avec mention "à compléter", "à remplir", "fourni en annexe" → "completion"

Indices pour "redaction":
- Mémoire technique → "redaction"
- Note méthodologique → "redaction"
- Mémoire environnemental / RSE → "redaction"
- Fiches références / CV → "redaction"

Réponds UNIQUEMENT au format JSON suivant (sans markdown):
[
  {
    "title": "Titre du document (ex: Memoire Technique)",
    "description": "Description du contenu attendu dans ce document",
    "expected_format": "docx|xlsx|pdf|other",
    "content_type": "redaction|completion",
    "rfp_source": "Reference dans l'AO (ex: Article 5.2 du RC, page 12)",
    "suggested": true
  }
]

Valeurs de expected_format:
- "docx": document texte (mémoire, notes, rapports)
- "xlsx": tableur (BPU, DQE, DPGF, planning)
- "pdf": formulaires administratifs pré-remplis
- "other": autre format ou non précisé"""

        parts = [f"CONTENU DE L'APPEL D'OFFRES:\n{new_rfp_content[:80000]}"]

        if old_response_content:
            parts.append(
                f"ANCIENNE RÉPONSE (pour référence):\n{old_response_content[:30000]}"
            )

        user_prompt = "\n\n---\n\n".join(parts)
        user_prompt += (
            "\n\nAnalyse cet appel d'offres et identifie TOUS les documents "
            "et livrables que le candidat doit fournir."
        )

        response = await self.generate_streaming(
            system_prompt, user_prompt, temperature=0.2, max_tokens=8000,
            timeout=600, on_progress=on_progress,
        )
        result = _parse_json_array(response)
        if result:
            return result

        logger.warning("Deliverable detection: JSON parse failed. First 500: %s", response[:500])
        return []

    async def generate_response_structure_for_document(
        self,
        document_title: str,
        document_description: str,
        new_rfp_content: str,
        old_rfp_content: str = "",
        old_response_content: str = "",
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> List[Dict]:
        """Generate chapter structure for a specific response document."""
        system_prompt = f"""Tu es un expert senior en réponse aux appels d'offres.

Tu dois créer la STRUCTURE DÉTAILLÉE (chapitrage) du document suivant:
**{document_title}**

Description: {document_description}

## Règles:
- Crée une structure adaptée spécifiquement à CE document (pas à l'ensemble de la réponse)
- Les chapitres doivent couvrir tous les aspects attendus pour ce type de document
- Utilise la structure de l'ancienne réponse comme référence si disponible
- Les descriptions doivent être précises et indiquer clairement le contenu attendu
- Le champ rfp_requirement doit citer l'exigence de l'AO concernée

Réponds UNIQUEMENT au format JSON suivant (sans markdown):
[
  {{
    "title": "Titre du chapitre",
    "description": "Description détaillée du contenu attendu",
    "chapter_type": "chapter",
    "rfp_requirement": "Exigence de l'AO correspondante",
    "children": [
      {{
        "title": "Sous-chapitre",
        "description": "Description",
        "chapter_type": "sub_chapter",
        "rfp_requirement": "Exigence",
        "children": []
      }}
    ]
  }}
]"""

        parts = [f"CONTENU DU NOUVEL APPEL D'OFFRES:\n{new_rfp_content[:60000]}"]
        if old_rfp_content:
            parts.append(f"CONTENU DE L'ANCIEN AO:\n{old_rfp_content[:30000]}")
        if old_response_content:
            parts.append(f"ANCIENNE RÉPONSE:\n{old_response_content[:30000]}")

        user_prompt = "\n\n---\n\n".join(parts)
        user_prompt += (
            f"\n\nGénère la structure complète du document '{document_title}' "
            "en te basant sur les exigences de l'AO."
        )

        response = await self.generate_streaming(
            system_prompt, user_prompt, temperature=0.2, max_tokens=8000,
            timeout=600, on_progress=on_progress,
        )
        result = _parse_json_array(response)
        if result:
            return result

        logger.warning("Doc structure gen failed for '%s'. First 500: %s",
                       document_title, response[:500])
        return []

    async def generate_chapter_content(
        self,
        chapter_title: str,
        chapter_description: str,
        rfp_requirement: str,
        old_response_content: str = "",
        context_chunks: str = "",
        improvement_axes: str = "",
        notes: str = "",
    ) -> str:
        """Generate or enrich content for a chapter."""
        system_prompt = """Tu es un rédacteur expert en réponses aux appels d'offres.
Tu dois rédiger un contenu professionnel, précis et convaincant pour un chapitre de réponse.

Règles:
- Style professionnel et persuasif
- Répondre précisément aux exigences de l'appel d'offres
- Mettre en valeur les compétences et l'expérience
- Être factuel et concret

Formatage:
- Utilise des sous-titres avec ## pour les sections
- Utilise **gras** pour les termes importants
- Utilise des listes à puces avec - pour les énumérations
- Structure en paragraphes clairs et aérés"""

        parts = [f"Chapitre: {chapter_title}"]
        if chapter_description:
            parts.append(f"Description: {chapter_description}")
        if rfp_requirement:
            parts.append(f"Exigence de l'AO: {rfp_requirement}")
        if old_response_content:
            parts.append(f"Contenu de l'ancienne réponse (à adapter et améliorer):\n{old_response_content[:5000]}")
        if context_chunks:
            parts.append(f"Éléments de contexte pertinents:\n{context_chunks[:3000]}")
        if improvement_axes:
            parts.append(f"Axes d'amélioration indiqués par le client:\n{improvement_axes}")
        if notes:
            parts.append(f"Notes additionnelles:\n{notes}")

        user_prompt = "\n\n".join(parts)
        user_prompt += "\n\nRédige le contenu complet pour ce chapitre."

        return await self.generate(system_prompt, user_prompt, temperature=0.4, max_tokens=6000)

    async def enrich_content(
        self,
        content: str,
        chapter_title: str,
        rfp_requirement: str = "",
        improvement_axes: str = "",
    ) -> str:
        """Enrich existing chapter content."""
        system_prompt = """Tu es un rédacteur expert en réponses aux appels d'offres.
Tu dois enrichir et améliorer le contenu existant d'un chapitre.

Règles:
- Conserver les informations existantes
- Ajouter des détails, exemples et arguments supplémentaires
- Améliorer le style et la clarté
- Rendre le contenu plus convaincant
- Retourner uniquement le texte enrichi

Formatage:
- Utilise des sous-titres avec ## pour les sections
- Utilise **gras** pour les termes importants
- Utilise des listes à puces avec - pour les énumérations"""

        user_prompt = f"""Chapitre: {chapter_title}
Exigence AO: {rfp_requirement}
Axes d'amélioration: {improvement_axes}

Contenu actuel à enrichir:
{content}

Enrichis et améliore ce contenu."""

        return await self.generate(system_prompt, user_prompt, temperature=0.4)

    async def analyze_compliance(
        self, response_content: str, rfp_requirements: str
    ) -> Dict:
        """Analyze exhaustiveness and compliance of the response."""
        system_prompt = """Tu es un expert en évaluation de réponses aux appels d'offres.
Analyse si la réponse couvre toutes les exigences de l'appel d'offres.

Réponds au format JSON (sans markdown):
{
  "score": 0-100,
  "covered_requirements": [{"requirement": "...", "coverage": "complete|partial|missing", "comment": "..."}],
  "missing_elements": [{"requirement": "...", "description": "ce qui manque"}],
  "recommendations": ["..."],
  "summary": "..."
}"""

        user_prompt = f"""EXIGENCES DE L'APPEL D'OFFRES:
{rfp_requirements[:10000]}

CONTENU DE LA RÉPONSE:
{response_content[:10000]}

Analyse l'exhaustivité et la conformité de cette réponse."""

        response = await self.generate(system_prompt, user_prompt, temperature=0.2, max_tokens=6000)
        result = _parse_json_object(response)
        if result:
            return result
        logger.warning("Compliance analysis: JSON parse failed. First 300 chars: %s", response[:300])
        return {"score": 0, "summary": response[:2000], "covered_requirements": [],
                "missing_elements": [], "recommendations": []}

    async def describe_image(self, image_context: str, surrounding_text: str) -> Dict:
        """Generate description and tags for an extracted image."""
        system_prompt = """Tu es un assistant qui analyse des images dans des documents d'appels d'offres.
À partir du contexte, génère une description et des tags pour cette image.

Réponds au format JSON (sans markdown):
{
  "description": "Description détaillée de l'image probable",
  "tags": ["tag1", "tag2"],
  "suggested_chapters": ["chapitres où cette image serait pertinente"]
}"""

        user_prompt = f"""Contexte de l'image (texte environnant dans le document):
{surrounding_text[:2000]}

Informations additionnelles: {image_context}

Décris cette image et suggère des tags et chapitres pertinents."""

        response = await self.generate(system_prompt, user_prompt, temperature=0.3)
        result = _parse_json_object(response)
        if result:
            return result
        return {"description": "", "tags": [], "suggested_chapters": []}

    async def generate_fill_content(
        self,
        document_title: str,
        document_description: str,
        expected_format: str,
        new_rfp_content: str,
        old_response_content: str = "",
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> str:
        """Generate fill-in content/instructions for a completion-type document (BPU, DQE, forms, etc.).

        Instead of generating chapters of text, this generates structured fill-in guidance
        that tells the user what values to put in each field/cell of the template document.
        """
        system_prompt = f"""Tu es un expert senior en réponse aux appels d'offres, spécialisé dans le remplissage
de documents types fournis par l'acheteur.

Le document à compléter est: **{document_title}**
Format attendu: {expected_format.upper()}
Description: {document_description}

## Ta mission:
Tu dois générer le CONTENU DE REMPLISSAGE pour ce document, c'est-à-dire les valeurs,
textes et données à inscrire dans les différents champs/cellules/rubriques du document.

## Règles selon le type de document:

### Si c'est un BPU (Bordereau des Prix Unitaires) ou DQE/DPGF:
- Génère un tableau markdown avec les colonnes: Poste / Désignation / Unité / Prix unitaire HT / Observations
- Base-toi sur les prestations décrites dans le CCTP/CCP de l'AO
- Pour les prix, indique "[A COMPLÉTER - prix]" car les prix sont confidentiels
- Indique les unités appropriées (forfait, jour, heure, m², etc.)
- Ajoute des observations sur le périmètre de chaque poste

### Si c'est un formulaire administratif (DC1, DC2, ATTRI1, etc.):
- Liste chaque rubrique/champ du formulaire
- Indique la valeur à renseigner ou "[A COMPLÉTER]" pour les données confidentielles
- Précise les documents justificatifs à joindre

### Si c'est un Acte d'Engagement:
- Identifie les champs à remplir (raison sociale, montants, lots, etc.)
- Indique les valeurs connues et "[A COMPLÉTER]" pour les montants

### Si c'est un cadre de réponse technique:
- Réponds point par point aux questions/rubriques imposées
- Fournis du contenu professionnel et détaillé pour chaque rubrique

## Format de sortie:
Génère le contenu en Markdown structuré avec:
- Des titres ## pour chaque section/onglet du document
- Des tableaux markdown pour les données tabulaires
- Des listes à puces pour les champs à remplir
- **[A COMPLÉTER]** pour les valeurs que seul le candidat connaît (prix, coordonnées exactes, etc.)
- Du contenu rédigé pour les rubriques textuelles

Utilise les informations de l'AO et de l'ancienne réponse pour pré-remplir un maximum de champs."""

        parts = [f"CONTENU DE L'APPEL D'OFFRES:\n{new_rfp_content[:60000]}"]
        if old_response_content:
            parts.append(f"ANCIENNE RÉPONSE (pour référence):\n{old_response_content[:30000]}")

        user_prompt = "\n\n---\n\n".join(parts)
        user_prompt += (
            f"\n\nGénère le contenu de remplissage complet pour le document '{document_title}' "
            f"({expected_format.upper()}) en te basant sur les exigences de l'AO."
        )

        return await self.generate_streaming(
            system_prompt, user_prompt, temperature=0.3, max_tokens=8000,
            timeout=600, on_progress=on_progress,
        )

    async def execute_custom_prompt(self, content: str, prompt: str, context: str = "") -> str:
        """Execute a custom user prompt on content."""
        system_prompt = """Tu es un assistant expert en rédaction de réponses aux appels d'offres.
Applique exactement l'instruction de l'utilisateur au contenu fourni.
Retourne uniquement le texte modifié.

Formatage:
- Utilise des sous-titres avec ## pour les sections
- Utilise **gras** pour les termes importants
- Utilise des listes à puces avec - pour les énumérations"""

        user_prompt = f"""Contexte: {context}

Instruction: {prompt}

Contenu:
{content}

Applique l'instruction au contenu."""

        return await self.generate(system_prompt, user_prompt, temperature=0.4)


async def run_parallel_ai_tasks(tasks: List[dict], ai_service: MistralAIService) -> List[str]:
    """Run multiple AI generation tasks in parallel.

    Args:
        tasks: List of dicts with system_prompt, user_prompt keys
        ai_service: The AI service instance

    Returns:
        List of generated texts in the same order as input tasks
    """
    coroutines = [
        ai_service.generate(
            task["system_prompt"],
            task["user_prompt"],
            temperature=task.get("temperature", 0.4),
        )
        for task in tasks
    ]
    return await asyncio.gather(*coroutines)
