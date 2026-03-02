"""AI service for LLM integration (Mistral API + Ollama)."""
import asyncio
import json
import logging
import re
from typing import Awaitable, Callable, List, Optional, Dict

import httpx
from mistralai import Mistral

from ..models.project import AIConfig

logger = logging.getLogger(__name__)


# ── Identity & anti-hallucination guardrail ─────────────────────────
def _build_identity_block(company_name: str = "", client_name: str = "") -> str:
    """Build a prompt block clarifying who is the respondent vs. the client.

    This prevents the LLM from confusing the two entities (e.g. attributing
    the respondent's products to the client, or describing the client's
    organization as if it were the respondent's).
    """
    lines = []
    lines.append("\n## IDENTITÉ ET RÔLES — RÈGLES ABSOLUES")

    if company_name and client_name:
        lines.append(f"- Tu rédiges pour le compte de **{company_name}** (le soumissionnaire/prestataire/candidat).")
        lines.append(f"- Le CLIENT (donneur d'ordres / acheteur) est **{client_name}**.")
        lines.append(f"- **{company_name}** et **{client_name}** sont DEUX entités DISTINCTES. Ne les confonds JAMAIS.")
        lines.append(f"- Les produits, filiales, compétences et références que tu décris sont ceux de **{company_name}**, PAS de **{client_name}**.")
        lines.append(f"- **{client_name}** est l'entité qui a publié l'appel d'offres et qui évalue la réponse.")
    elif company_name:
        lines.append(f"- Tu rédiges pour le compte de **{company_name}** (le soumissionnaire/prestataire/candidat).")
        lines.append(f"- Ne confonds JAMAIS l'identité du soumissionnaire avec celle du client.")
    elif client_name:
        lines.append(f"- Le CLIENT (donneur d'ordres / acheteur) est **{client_name}**.")
        lines.append(f"- Ne confonds JAMAIS l'identité du client avec celle du soumissionnaire.")

    lines.append("")
    lines.append("## INTERDICTIONS ABSOLUES — ANTI-HALLUCINATION")
    lines.append("- Tu ne dois JAMAIS inventer, fabriquer ou supposer des informations factuelles qui ne figurent pas dans les documents fournis.")
    lines.append("- N'invente JAMAIS de filiales, entités juridiques, numéros SIREN, capitaux sociaux, dates de création, formes juridiques ou tout autre détail administratif.")
    lines.append("- N'invente JAMAIS de chiffres, statistiques, pourcentages de performance, montants financiers ou résultats de projets.")
    lines.append("- N'invente JAMAIS de noms de produits, solutions, plateformes ou outils sauf s'ils sont explicitement mentionnés dans les documents fournis.")
    lines.append("- N'attribue JAMAIS les produits ou compétences du soumissionnaire au client, ni inversement.")
    lines.append("- Si une information factuelle te manque (nom de filiale, chiffre, référence), utilise un marqueur explicite comme « [À COMPLÉTER] » ou « [INFORMATION À FOURNIR PAR L'ÉQUIPE] » plutôt que d'inventer.")
    lines.append("- Quand tu mentionnes des capacités ou références, base-toi UNIQUEMENT sur les documents fournis (ancienne réponse, documents d'inspiration, contexte). Si aucun document ne mentionne un fait, ne l'affirme pas.")

    return "\n".join(lines)


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
    def from_config(cls, config: AIConfig, decrypted_key: str = "") -> "MistralAIService":
        """Create from DB config. Prefer using create_ai_service() factory instead."""
        return cls(
            api_key=decrypted_key or config.mistral_api_key_encrypted or "",
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

        # Scale stream-init timeout with input size: large prompts need more
        # TTFT (time-to-first-token) because the model must process the full
        # context before emitting anything.  Base 60s + 1s per 5K input chars.
        init_timeout = max(60, 60 + input_chars // 5000)
        logger.info("Stream init timeout: %ds (input ~%d chars)", init_timeout, input_chars)

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
                timeout=init_timeout,
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
            logger.error("Mistral stream init timed out after %ds (input ~%d chars)", init_timeout, input_chars)
            raise TimeoutError(f"L'appel IA a expire apres {init_timeout}s en attendant le debut du stream.")

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
        ai_context: str = "",
        company_name: str = "",
        client_name: str = "",
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

## IMPORTANT — Documents EXCLUS de la structure:
NE GÉNÈRE PAS de chapitres pour les documents suivants car ils sont FOURNIS par l'acheteur et doivent
simplement être COMPLÉTÉS/REMPLIS (pas rédigés). Ils sont traités séparément:
- BPU (Bordereau des Prix Unitaires) — tableur Excel à compléter
- DQE (Détail Quantitatif Estimatif) — tableur Excel à compléter
- DPGF (Décomposition du Prix Global Forfaitaire) — tableur Excel à compléter
- Formulaires administratifs pré-formatés: DC1, DC2, DC3, DC4, ATTRI1, NOTI1, NOTI2
- Acte d'Engagement (AE) pré-formaté fourni par l'acheteur
- Cadres de réponse imposés à remplir (quand l'acheteur fournit un document à compléter)
- Tout document décrit comme "à compléter", "à remplir", "fourni en annexe à remplir"

Génère la structure UNIQUEMENT pour les documents à RÉDIGER: mémoire technique, notes méthodologiques,
planning détaillé rédigé, mémoire environnemental/RSE, fiches références/CV rédigées, etc.

## Règles pour la structure:
- Chaque exigence RÉDACTIONNELLE du nouvel AO DOIT être couverte par au moins un chapitre/sous-chapitre
- Les chapitres suivent l'ordre logique attendu par l'acheteur (souvent celui du RC/CCTP)
- Inclure les chapitres administratifs (présentation société, références, moyens, etc.)
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

        # Add identity and anti-hallucination guardrails
        system_prompt += _build_identity_block(company_name, client_name)

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

        if ai_context:
            parts.append(f"CONTEXTE DE RÉDACTION (fourni par l'utilisateur pour orienter la réponse):\n{ai_context}")

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

Ta mission est d'analyser le contenu d'un appel d'offres pour identifier les DOCUMENTS PHYSIQUEMENT DISTINCTS
que le candidat doit fournir dans sa réponse.

## RÈGLE FONDAMENTALE — NE PAS ÉCLATER LES DOCUMENTS:
Tu dois identifier UNIQUEMENT les documents qui sont **physiquement séparés** (fichiers distincts à remettre).
Ne crée PAS un livrable séparé pour chaque thématique ou section d'un même document.

Exemples de ce qu'il NE FAUT PAS faire:
- NE PAS séparer "Fiches de références" en un document distinct si elles font partie du mémoire technique
- NE PAS séparer "CV des intervenants" en un document distinct s'ils sont une section du mémoire technique
- NE PAS séparer "Note méthodologique" si c'est un chapitre du mémoire technique
- NE PAS séparer "Planning" si c'est une section du mémoire technique
- NE PAS séparer "Mémoire RSE/environnemental" si c'est une section du mémoire technique

Ces éléments (références, CV, méthodologie, planning, RSE) sont des CHAPITRES à l'intérieur du mémoire technique,
pas des documents séparés. Ils seront gérés comme des chapitres lors de la génération de la structure.

## Quand créer un document SÉPARÉ:
- L'AO demande EXPLICITEMENT un document séparé (ex: "fournir un document distinct", "fichier séparé")
- C'est un fichier d'un FORMAT DIFFÉRENT (ex: BPU en Excel vs mémoire en Word)
- C'est un formulaire administratif officiel (DC1, DC2, ATTRI1, etc.)
- L'AO mentionne clairement que ce document est une PIÈCE DISTINCTE de la candidature

## Documents typiques à identifier:
- Le mémoire technique (UN SEUL document regroupant toute l'offre technique: méthodologie, moyens, planning, références, CV, RSE, etc.)
- L'acte d'engagement (AE) — si formulaire séparé
- Le bordereau des prix unitaires (BPU) — fichier Excel séparé
- Le DQE/DPGF — fichier Excel séparé
- Les formulaires obligatoires (DC1, DC2, ATTRI1, etc.) — chacun est un formulaire séparé
- Les annexes EXPLICITEMENT demandées comme fichiers séparés

## Règles:
- Base-toi UNIQUEMENT sur ce que l'AO demande explicitement
- Cite la source dans l'AO (article, page, section) quand possible
- En cas de doute, REGROUPE dans le mémoire technique plutôt que de créer un document séparé
- Vise un nombre RAISONNABLE de documents (typiquement 3-8 pour un AO standard)
- Si une ancienne réponse est fournie, utilise-la pour confirmer la liste des fichiers PHYSIQUES remis

## IMPORTANT - Classification du type de contenu (content_type):
Tu DOIS classifier chaque livrable selon son type de contenu:

- "redaction": Document à RÉDIGER entièrement par le candidat (mémoire technique, etc.)
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
- Mémoire technique → "redaction" (UN SEUL document, pas plusieurs)

Réponds UNIQUEMENT au format JSON suivant (sans markdown):
[
  {
    "title": "Titre du document (ex: Memoire Technique)",
    "description": "Description du contenu attendu dans ce document, incluant toutes les sections/thématiques qui en font partie",
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

    async def summarize_rfp_for_structure(
        self,
        rfp_content: str,
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> str:
        """Create a focused summary of the RFP for per-document structure generation.

        This allows per-document AI calls to use a compact ~4K summary instead of
        the full 60-80K RFP content, drastically reducing prompt size and latency.
        """
        system_prompt = """Tu es un expert en analyse d'appels d'offres.

Tu dois créer un RÉSUMÉ STRUCTURÉ et COMPLET de cet appel d'offres, en extrayant:
1. L'objet du marché et contexte général
2. TOUTES les exigences techniques (CCTP, spécifications)
3. TOUTES les exigences administratives et réglementaires
4. Les critères de jugement des offres et leur pondération
5. Les lots et allotissement
6. Les contraintes de délais, planning, pénalités
7. Les compétences et moyens demandés
8. Les annexes et documents à fournir

Sois EXHAUSTIF sur les exigences. Chaque exigence doit être clairement identifiée avec sa source (article, section, page).
Le résumé doit permettre de créer la structure complète d'une réponse sans avoir à relire l'AO original.

Format: texte structuré avec des titres markdown. Pas de JSON."""

        user_prompt = f"CONTENU COMPLET DE L'APPEL D'OFFRES:\n{rfp_content[:80000]}\n\n"
        user_prompt += "Crée un résumé structuré et exhaustif de cet AO."

        return await self.generate_streaming(
            system_prompt, user_prompt, temperature=0.1, max_tokens=6000,
            timeout=300, on_progress=on_progress,
        )

    async def generate_response_structure_for_document(
        self,
        document_title: str,
        document_description: str,
        new_rfp_content: str,
        old_rfp_content: str = "",
        old_response_content: str = "",
        rfp_summary: str = "",
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
        ai_context: str = "",
        company_name: str = "",
        client_name: str = "",
    ) -> List[Dict]:
        """Generate chapter structure for a specific response document (redaction type only)."""
        system_prompt = f"""Tu es un expert senior en réponse aux appels d'offres.

Tu dois créer la STRUCTURE DÉTAILLÉE (chapitrage) du document suivant, qui est un document À RÉDIGER:
**{document_title}**

Description: {document_description}

Ce document nécessite une RÉDACTION complète (texte, argumentation, démonstration).
Ce n'est PAS un formulaire à remplir ni un tableur à compléter.

## Règles:
- Crée une structure adaptée spécifiquement à CE document à rédiger (pas à l'ensemble de la réponse)
- Les chapitres doivent couvrir tous les aspects rédactionnels attendus pour ce type de document
- Utilise la structure de l'ancienne réponse comme référence si disponible
- Les descriptions doivent être précises et indiquer clairement le contenu à rédiger
- Le champ rfp_requirement doit citer l'exigence de l'AO concernée
- N'inclus PAS de chapitres pour des documents annexes à compléter (BPU, DQE, formulaires) — ils sont traités séparément

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

        # Add identity and anti-hallucination guardrails
        system_prompt += _build_identity_block(company_name, client_name)

        # Use the pre-computed summary if available (much smaller prompt),
        # otherwise fall back to truncated full content.
        parts = []
        if rfp_summary:
            parts.append(f"RÉSUMÉ STRUCTURÉ DE L'APPEL D'OFFRES:\n{rfp_summary}")
        else:
            parts.append(f"CONTENU DU NOUVEL APPEL D'OFFRES:\n{new_rfp_content[:60000]}")
        if old_rfp_content:
            parts.append(f"CONTENU DE L'ANCIEN AO:\n{old_rfp_content[:30000]}")
        if old_response_content:
            parts.append(f"ANCIENNE RÉPONSE:\n{old_response_content[:30000]}")
        if ai_context:
            parts.append(f"CONTEXTE DE RÉDACTION (fourni par l'utilisateur pour orienter la réponse):\n{ai_context}")

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
        ai_context: str = "",
        inspiration_content: str = "",
        company_name: str = "",
        client_name: str = "",
    ) -> str:
        """Generate or enrich content for a chapter."""
        system_prompt = """Tu es un rédacteur senior expert en réponses aux appels d'offres, avec 15 ans d'expérience dans la rédaction de mémoires techniques gagnants.

Tu dois rédiger un contenu de HAUTE QUALITÉ RÉDACTIONNELLE pour un chapitre de réponse à un appel d'offres.

## Style de rédaction OBLIGATOIRE :
- **Phrases développées et argumentées** : chaque idée doit être expliquée, contextualisée et justifiée. Pas de phrases télégraphiques ni de style "fiche synthèse".
- **Ton professionnel mais humain** : rédige comme un expert qui s'adresse à un évaluateur. Utilise des formulations engageantes et convaincantes, pas un style robotique.
- **Paragraphes étoffés** : chaque paragraphe doit contenir 3 à 6 phrases minimum. Développe les arguments, donne des exemples concrets, explique le "pourquoi" et le "comment".
- **Transitions fluides** : utilise des phrases de transition entre les sections et paragraphes (ex: "Fort de cette expertise,", "Dans cette optique,", "Afin de répondre pleinement à cette exigence,", "Cette approche s'inscrit dans une démarche globale de...").
- **Vocabulaire riche et varié** : évite les répétitions, utilise des synonymes, des formulations professionnelles variées.
- **Arguments structurés** : pour chaque point, présente le contexte, la solution proposée, les bénéfices attendus et si possible un exemple ou une preuve de capacité.
- **Longueur attendue** : un chapitre doit faire au minimum 300 mots. Un sous-chapitre au minimum 150 mots. Ne sois JAMAIS trop bref.

## Ce qu'il faut ÉVITER absolument :
- Les listes à puces sèches sans phrases d'introduction ni de conclusion
- Les phrases trop courtes de type "Nous proposons X." sans explication
- Le style "résumé exécutif" ou "synthèse" — c'est un mémoire technique DÉTAILLÉ
- Les paragraphes d'une seule phrase
- Le copier-coller mécanique de l'exigence sans valeur ajoutée

## Règles de contenu :
- Répondre précisément et exhaustivement aux exigences de l'appel d'offres
- Mettre en valeur les compétences, l'expérience et la méthodologie du SOUMISSIONNAIRE (pas du client)
- Être factuel et concret tout en restant développé et argumenté
- Apporter de la valeur ajoutée : ne pas simplement reformuler l'exigence, mais montrer COMMENT on y répond
- Ne JAMAIS décrire l'organisation, les filiales ou les produits du CLIENT — tu décris ceux du SOUMISSIONNAIRE

## Anonymisation :
- Le texte fourni peut contenir des marqueurs anonymisés comme [ENTREPRISE_1], [SOLUTION_1], [PERSONNE_1], etc.
- Tu DOIS réutiliser EXACTEMENT les mêmes marqueurs présents dans le texte fourni.
- Tu ne dois JAMAIS inventer de nouveaux marqueurs.
- Si tu dois mentionner une entité générique qui n'a pas de marqueur, utilise des termes génériques (ex: "le client", "le prestataire", "la solution proposée").

## Formatage :
- Utilise **##** pour les titres de sections et **###** pour les sous-sections
- Utilise **gras** pour les termes clés et les concepts importants
- Utilise des listes à puces **uniquement** pour les énumérations de 3+ éléments, et toujours avec une phrase d'introduction et idéalement une phrase de conclusion
- Utilise des tableaux markdown quand c'est pertinent (comparaisons, plannings, matrices)
- Structure en paragraphes clairs, aérés et DÉVELOPPÉS
- Sépare les sections par des lignes vides pour la lisibilité"""

        # Add identity and anti-hallucination guardrails
        system_prompt += _build_identity_block(company_name, client_name)

        if ai_context:
            system_prompt += f"""

Contexte de rédaction fourni par l'utilisateur (utilise-le pour orienter le ton, le style et le contenu):
{ai_context}"""

        parts = [f"Chapitre: {chapter_title}"]
        if chapter_description:
            parts.append(f"Description: {chapter_description}")
        if rfp_requirement:
            parts.append(f"Exigence de l'AO: {rfp_requirement}")
        if old_response_content:
            parts.append(f"Contenu de l'ancienne réponse (à adapter et améliorer):\n{old_response_content[:5000]}")
        if context_chunks:
            parts.append(f"Éléments de contexte pertinents:\n{context_chunks[:3000]}")
        if inspiration_content:
            parts.append(f"Contenu d'inspiration (provenant d'autres réponses — utilise les idées et la structure pertinentes, mais NE REPRENDS PAS les noms de clients, projets ou entreprises qui y figurent) :\n{inspiration_content[:4000]}")
        if improvement_axes:
            parts.append(f"Axes d'amélioration indiqués par le client:\n{improvement_axes}")
        if notes:
            parts.append(f"Notes additionnelles:\n{notes}")

        user_prompt = "\n\n".join(parts)
        user_prompt += "\n\nRédige le contenu COMPLET et DÉVELOPPÉ pour ce chapitre. Chaque section doit être argumentée avec des paragraphes de plusieurs phrases."

        return await self.generate(system_prompt, user_prompt, temperature=0.4, max_tokens=8000)

    async def enrich_content(
        self,
        content: str,
        chapter_title: str,
        rfp_requirement: str = "",
        improvement_axes: str = "",
        ai_context: str = "",
        company_name: str = "",
        client_name: str = "",
    ) -> str:
        """Enrich existing chapter content."""
        system_prompt = """Tu es un rédacteur senior expert en réponses aux appels d'offres.
Tu dois enrichir et améliorer significativement le contenu existant d'un chapitre.

## Objectif d'enrichissement :
- **Développer chaque paragraphe** : transformer les phrases courtes en paragraphes argumentés de 3-6 phrases
- **Ajouter de la substance** : exemples concrets, justifications, bénéfices attendus, preuves de capacité
- **Améliorer les transitions** : ajouter des phrases de liaison entre sections pour un texte fluide
- **Renforcer l'argumentation** : pour chaque affirmation, ajouter le "pourquoi" et le "comment"
- **Enrichir le vocabulaire** : remplacer les formulations génériques par des termes précis et professionnels
- **Conserver toutes les informations existantes** tout en les développant
- Le texte enrichi doit être au moins 50% plus long que l'original
- Ne JAMAIS ajouter de faits inventés (chiffres, filiales, produits) qui ne sont pas dans le texte original

## Anonymisation :
- Le texte fourni peut contenir des marqueurs anonymisés comme [ENTREPRISE_1], [SOLUTION_1], [PERSONNE_1], etc.
- Tu DOIS réutiliser EXACTEMENT les mêmes marqueurs présents dans le texte fourni.
- Tu ne dois JAMAIS inventer de nouveaux marqueurs.
- Si tu dois mentionner une entité générique qui n'a pas de marqueur, utilise des termes génériques.

## Formatage :
- Utilise **##** pour les titres de sections et **###** pour les sous-sections
- Utilise **gras** pour les termes clés
- Utilise des listes à puces avec une phrase d'introduction, jamais des listes "sèches"
- Utilise des tableaux markdown quand pertinent
- Structure en paragraphes développés et aérés"""

        # Add identity and anti-hallucination guardrails
        system_prompt += _build_identity_block(company_name, client_name)

        if ai_context:
            system_prompt += f"""

Contexte de rédaction fourni par l'utilisateur (utilise-le pour orienter le ton, le style et le contenu):
{ai_context}"""

        user_prompt = f"""Chapitre: {chapter_title}
Exigence AO: {rfp_requirement}
Axes d'amélioration: {improvement_axes}

Contenu actuel à enrichir:
{content}

Enrichis et développe significativement ce contenu. Chaque section doit être plus argumentée, avec des paragraphes complets et des transitions fluides. Le résultat doit ressembler à un vrai mémoire technique professionnel, pas à une synthèse."""

        return await self.generate(system_prompt, user_prompt, temperature=0.4, max_tokens=8000)

    async def analyze_compliance(
        self, response_content: str, rfp_requirements: str,
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> Dict:
        """Analyze exhaustiveness and compliance of the response."""
        system_prompt = """Tu es un expert senior en évaluation de réponses aux appels d'offres publics et privés.
Ta mission: vérifier que le mémoire technique et les documents de réponse couvrent TOUTES les exigences
extraites des pièces du dossier de consultation (CCAP, CCTP, RC, etc.).

## Contexte des documents d'appel d'offres (AO)
Les documents AO sont structurés avec des marqueurs === DOCUMENT: nom_du_fichier ===.
Ils peuvent inclure:
- **CCTP** (Cahier des Clauses Techniques Particulières): exigences techniques, prestations attendues,
  livrables, niveaux de service, spécifications fonctionnelles et techniques.
- **CCAP** (Cahier des Clauses Administratives Particulières): exigences administratives, délais,
  pénalités, modalités d'exécution, assurances, sous-traitance, conditions financières.
- **RC** (Règlement de Consultation): critères de jugement, forme de la réponse attendue.
- Autres pièces: BPU, DQE, annexes techniques, etc.

## Contexte de la réponse
La réponse peut contenir:
- Le **Mémoire Technique** rédigé par l'outil (marqué === DOCUMENT: Memoire Technique ===),
  structuré en chapitres (--- Titre du chapitre ---). C'est souvent le document PRINCIPAL de la réponse.
- Des documents complémentaires uploadés (fiches techniques, attestations, tableaux Excel, etc.).

## Règles d'analyse
1. Extrais CHAQUE exigence significative des documents AO (CCTP + CCAP + autres).
2. Vérifie si cette exigence est couverte dans la réponse (mémoire technique OU documents complémentaires).
3. Ne marque PAS une exigence comme manquante si elle est couverte quelque part dans le contenu,
   même dans une section différente ou un document séparé.
4. Pour les exigences du CCTP: vérifie la couverture technique (méthodologie, moyens, organisation).
5. Pour les exigences du CCAP: vérifie les engagements administratifs (délais, pénalités, conformités).
6. Sois PRÉCIS sur ce qui manque: ne dis pas juste "non couvert", explique CE QUI manque concrètement.
7. Analyse l'INTÉGRALITÉ du contenu fourni: technique, RSE, qualité, sécurité, environnement, etc.

Réponds au format JSON (sans markdown):
{
  "score": 0-100,
  "covered_requirements": [{"requirement": "...", "coverage": "complete|partial|missing", "comment": "...", "source_rfp": "nom du document AO source (ex: CCTP, CCAP)", "source_response": "nom du document/chapitre de réponse couvrant cette exigence"}],
  "missing_elements": [{"requirement": "...", "description": "ce qui manque concrètement dans la réponse", "source_rfp": "nom du document AO source"}],
  "recommendations": ["actions concrètes pour améliorer la conformité"],
  "summary": "..."
}

Pour source_rfp: indique le nom du document AO (CCTP, CCAP, RC, etc.) où l'exigence est mentionnée.
Pour source_response: indique le chapitre du mémoire technique ou le document qui couvre cette exigence."""

        user_prompt = f"""DOCUMENTS DE L'APPEL D'OFFRES (CCAP, CCTP, RC, annexes):
{rfp_requirements[:50000]}

CONTENU DE LA RÉPONSE (Mémoire Technique + documents complémentaires):
{response_content[:50000]}

Analyse l'exhaustivité et la conformité de cette réponse par rapport aux exigences de l'AO.
IMPORTANT:
- Parcours CHAQUE article/clause du CCTP et du CCAP pour vérifier sa couverture dans la réponse.
- Le Mémoire Technique est le document principal de la réponse – concentre-toi dessus en priorité.
- Indique pour chaque exigence le document AO source (CCTP art.X, CCAP art.Y) et le chapitre/document de réponse correspondant.
- Sois factuel et précis dans tes commentaires."""

        response = await self.generate_streaming(
            system_prompt, user_prompt, temperature=0.2, max_tokens=8000,
            timeout=600, on_progress=on_progress,
        )
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
        ai_context: str = "",
        company_name: str = "",
        client_name: str = "",
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

        # Add identity and anti-hallucination guardrails
        system_prompt += _build_identity_block(company_name, client_name)

        parts = [f"CONTENU DE L'APPEL D'OFFRES:\n{new_rfp_content[:60000]}"]
        if old_response_content:
            parts.append(f"ANCIENNE RÉPONSE (pour référence):\n{old_response_content[:30000]}")
        if ai_context:
            parts.append(f"CONTEXTE DE RÉDACTION (fourni par l'utilisateur pour orienter la réponse):\n{ai_context}")

        user_prompt = "\n\n---\n\n".join(parts)
        user_prompt += (
            f"\n\nGénère le contenu de remplissage complet pour le document '{document_title}' "
            f"({expected_format.upper()}) en te basant sur les exigences de l'AO."
        )

        return await self.generate_streaming(
            system_prompt, user_prompt, temperature=0.3, max_tokens=8000,
            timeout=600, on_progress=on_progress,
        )

    async def generate_excel_fill_data(
        self,
        document_title: str,
        excel_structure: str,
        new_rfp_content: str,
        old_response_content: str = "",
    ) -> List[Dict]:
        """Generate structured JSON data to fill an Excel document from old response data.

        Returns a list of dicts: [{"sheet": str, "cell": str, "value": str|number}, ...]
        """
        # Detect document type to adapt the prompt
        title_lower = document_title.lower()
        is_conformity = any(kw in title_lower for kw in [
            "rgpd", "conformit", "gdpr", "protection des données",
            "questionnaire", "grille", "annexe", "déclaration",
            "engagement", "certification", "audit", "sécurité",
            "environnement", "rse", "social", "qualité",
        ])
        is_pricing = any(kw in title_lower for kw in [
            "bpu", "bordereau", "dqe", "dpgf", "prix", "tarif", "chiffrage",
        ])

        if is_conformity and not is_pricing:
            doc_type_desc = "documents de conformité, questionnaires et grilles de réponse"
            fill_rules = """## Règles STRICTES:
1. Tu DOIS remplir TOUTES les cellules vides qui attendent une réponse du candidat
2. Pour les colonnes "Réponse", "Conformité", "Conforme", réponds par "Oui", "Non", "Partiel" ou "N/A" selon le contexte
3. Pour les colonnes "Commentaire", "Détail", "Description", "Mesures", fournis une réponse détaillée et pertinente
4. Reprends les informations de l'ancienne réponse quand elles existent
5. Si tu ne trouves pas l'information dans l'ancienne réponse, génère une réponse professionnelle basée sur le contexte de l'appel d'offres
6. Ne modifie PAS les cellules d'en-tête, de titre, de numérotation ou de structure
7. Ne remplis QUE les cellules qui sont vides (marquées "(vide)") et qui attendent une valeur du candidat
8. Pour les textes, utilise des chaînes de caractères claires et professionnelles"""
        else:
            doc_type_desc = "Bordereaux de Prix Unitaires (BPU), DQE et DPGF"
            fill_rules = """## Règles STRICTES:
1. Tu DOIS reprendre les informations de l'ancienne réponse quand elles existent (prix, textes, données entreprise, réponses, etc.)
2. Si une information n'existe pas dans l'ancienne réponse, mets la valeur "[A COMPLÉTER]"
3. Ne modifie PAS les cellules d'en-tête, de titre ou de structure (lignes d'entête, titres de colonnes)
4. Ne remplis QUE les cellules qui sont vides ou qui attendent une valeur du candidat
5. Pour les prix, utilise des NOMBRES (pas de texte) : 150.00, pas "150,00 €"
6. Pour les textes (désignations, observations), utilise des chaînes de caractères"""

        system_prompt = f"""Tu es un expert senior en réponse aux appels d'offres, spécialisé dans le remplissage
de {doc_type_desc}.

Le document à compléter est: **{document_title}**

## Ta mission:
Tu dois générer les VALEURS EXACTES à inscrire dans chaque cellule de l'Excel,
en te basant sur l'ancienne réponse et le contenu de l'appel d'offres.

{fill_rules}

## Format de sortie OBLIGATOIRE:
Retourne UNIQUEMENT un tableau JSON, sans texte avant ni après:
[
  {{"sheet": "Nom de l'onglet", "cell": "B5", "value": "Oui"}},
  {{"sheet": "Nom de l'onglet", "cell": "C5", "value": "Mesure mise en place..."}},
  ...
]

IMPORTANT: Tu DOIS générer une entrée pour CHAQUE cellule vide qui attend une réponse du candidat.
Analyse bien la structure de l'Excel pour identifier les colonnes de réponse.
Utilise les coordonnées Excel exactes (A1, B2, etc.) correspondant à la structure fournie."""

        # Put context FIRST so it's most prominent, then Excel structure, then RFP
        parts = []
        if old_response_content:
            parts.append(
                f"⚠️ ANCIENNE RÉPONSE (CONTIENT LES INFORMATIONS À REPRENDRE EN PRIORITÉ):\n{old_response_content[:50000]}"
            )
        parts.append(f"STRUCTURE DE L'EXCEL À REMPLIR:\n{excel_structure[:40000]}")
        parts.append(f"CONTENU DE L'APPEL D'OFFRES (pour contexte):\n{new_rfp_content[:20000]}")

        user_prompt = "\n\n---\n\n".join(parts)
        if is_conformity and not is_pricing:
            user_prompt += (
                f"\n\n⚠️ RAPPEL IMPORTANT: Génère le JSON de remplissage pour le document '{document_title}'. "
                "Ce document est un questionnaire/grille de conformité. "
                "Tu DOIS remplir TOUTES les cellules vides qui attendent une réponse (colonnes Réponse, Commentaire, Détail, etc.). "
                "Pour chaque question/exigence, fournis une réponse appropriée (Oui/Non/Partiel + commentaire si nécessaire). "
                "Retourne UNIQUEMENT le JSON."
            )
        else:
            user_prompt += (
                f"\n\n⚠️ RAPPEL IMPORTANT: Génère le JSON de remplissage pour le document '{document_title}'. "
                "Tu DOIS reprendre TOUTES les informations de l'ancienne réponse ci-dessus (prix, textes, réponses, données). "
                "Chaque cellule vide doit être remplie avec l'information correspondante de l'ancienne réponse. "
                "Retourne UNIQUEMENT le JSON."
            )

        raw = await self.generate(system_prompt, user_prompt, temperature=0.1, max_tokens=32000)

        # Parse the JSON response
        cleaned = _clean_json_response(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            repaired = _repair_truncated_json(cleaned, target="array")
            data = json.loads(repaired)

        if not isinstance(data, list):
            raise ValueError("AI response is not a JSON array")

        return data

    async def generate_pdf_fill_data(
        self,
        document_title: str,
        pdf_structure: str,
        new_rfp_content: str,
        old_response_content: str = "",
        has_form_fields: bool = False,
    ) -> List[Dict]:
        """Generate structured JSON data to fill a PDF form/document.

        For form PDFs:  [{"field": "field_name", "value": "..."}, ...]
        For zone PDFs:  [{"zone_id": "z0", "value": "..."}, ...]
        """

        if has_form_fields:
            output_format = """## Format de sortie OBLIGATOIRE (PDF avec champs de formulaire):
Retourne UNIQUEMENT un tableau JSON, sans texte avant ni après:
[
  {"field": "nom_du_champ", "value": "valeur à inscrire"},
  {"field": "autre_champ", "value": "autre valeur"},
  ...
]

Utilise EXACTEMENT les noms de champs tels qu'ils apparaissent dans la structure du PDF."""
        else:
            output_format = """## Format de sortie OBLIGATOIRE (PDF avec zones identifiées):
Le système a détecté des zones remplissables dans le PDF, chacune identifiée par un ID (z0, z1, z2, ...).
Pour chaque zone que tu veux remplir, donne l'ID et la valeur.

Retourne UNIQUEMENT un tableau JSON, sans texte avant ni après:
[
  {"zone_id": "z0", "value": "ACME Corporation"},
  {"zone_id": "z1", "value": "123 rue de la Paix, 75001 Paris"},
  {"zone_id": "z3", "value": "12345678901234"},
  ...
]

IMPORTANT:
- Utilise EXACTEMENT les zone_id tels qu'indiqués (z0, z1, z2, etc.)
- Ne remplis que les zones pour lesquelles tu as une valeur pertinente
- N'invente PAS de zone_id qui n'existent pas dans la liste"""

        system_prompt = f"""Tu es un expert senior en réponse aux appels d'offres, spécialisé dans le remplissage
de documents administratifs PDF (DC1, DC2, DC3, actes d'engagement, formulaires de candidature, etc.).

Le document à compléter est: **{document_title}**

## Ta mission:
Tu dois générer les VALEURS EXACTES à inscrire dans ce PDF,
en te basant sur l'ancienne réponse et les informations de l'entreprise.

## Règles STRICTES:
1. Tu DOIS reprendre les informations de l'ancienne réponse quand elles existent (raison sociale, SIRET, adresse, etc.)
2. Si une information n'existe pas dans l'ancienne réponse, mets la valeur "[A COMPLÉTER]"
3. Ne remplis QUE les champs/zones qui attendent une réponse du candidat
4. Pour les cases à cocher, utilise "X" ou "Oui"/"Non"
5. Pour les dates, utilise le format JJ/MM/AAAA
6. Pour les montants, utilise des nombres avec 2 décimales (ex: 15000.00)
7. TRÈS IMPORTANT — Valeurs COURTES: chaque valeur doit tenir sur UNE SEULE LIGNE dans le PDF.
   Maximum 60 caractères par valeur. Pas de phrases longues, pas de retours à la ligne.
   Exemple BON: "ACME SAS" / "12 rue de la Paix, 75001 Paris" / "01 23 45 67 89"
   Exemple MAUVAIS: "La société ACME SAS, immatriculée au RCS de Paris sous le numéro..."
8. Ne duplique PAS les informations du label dans ta valeur (si le label dit "Nom:", ne mets pas "Nom: ACME")

{output_format}"""

        parts = []
        if old_response_content:
            parts.append(
                f"⚠️ ANCIENNE RÉPONSE (CONTIENT LES INFORMATIONS ENTREPRISE À REPRENDRE EN PRIORITÉ):\n{old_response_content[:50000]}"
            )
        parts.append(f"STRUCTURE DU PDF ET ZONES REMPLISSABLES:\n{pdf_structure[:40000]}")
        parts.append(f"CONTENU DE L'APPEL D'OFFRES (pour contexte):\n{new_rfp_content[:20000]}")

        user_prompt = "\n\n---\n\n".join(parts)
        user_prompt += (
            f"\n\n⚠️ RAPPEL IMPORTANT: Génère le JSON de remplissage pour le document '{document_title}'. "
            "Tu DOIS reprendre TOUTES les informations connues de l'ancienne réponse (raison sociale, SIRET, adresse, "
            "représentant légal, etc.). Retourne UNIQUEMENT le JSON."
        )

        raw = await self.generate(system_prompt, user_prompt, temperature=0.1, max_tokens=32000)

        cleaned = _clean_json_response(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            repaired = _repair_truncated_json(cleaned, target="array")
            data = json.loads(repaired)

        if not isinstance(data, list):
            raise ValueError("AI response is not a JSON array")

        return data

    async def execute_custom_prompt(
        self, content: str, prompt: str, context: str = "", ai_context: str = "",
        company_name: str = "", client_name: str = "",
    ) -> str:
        """Execute a custom user prompt on content."""
        system_prompt = """Tu es un rédacteur senior expert en réponses aux appels d'offres.
Applique exactement l'instruction de l'utilisateur au contenu fourni.
Retourne uniquement le texte modifié.

Style de rédaction :
- Rédige des phrases développées et argumentées, pas de style télégraphique
- Utilise des transitions fluides entre les sections
- Chaque paragraphe doit contenir plusieurs phrases développées

Anonymisation :
- Le texte fourni peut contenir des marqueurs anonymisés comme [ENTREPRISE_1], [SOLUTION_1], [PERSONNE_1], etc.
- Tu DOIS réutiliser EXACTEMENT les mêmes marqueurs présents dans le texte fourni.
- Tu ne dois JAMAIS inventer de nouveaux marqueurs.
- Si tu dois mentionner une entité générique qui n'a pas de marqueur, utilise des termes génériques.

Formatage :
- Utilise **##** pour les titres de sections et **###** pour les sous-sections
- Utilise **gras** pour les termes clés
- Utilise des listes à puces avec phrases d'introduction, pas de listes sèches
- Utilise des tableaux markdown quand pertinent"""

        # Add identity and anti-hallucination guardrails
        system_prompt += _build_identity_block(company_name, client_name)

        if ai_context:
            system_prompt += f"""

Contexte de rédaction fourni par l'utilisateur (utilise-le pour orienter le ton, le style et le contenu):
{ai_context}"""

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


# ── Ollama provider ─────────────────────────────────────────────────


class OllamaAIService(MistralAIService):
    """AI service using a local Ollama instance for generation.

    Inherits all high-level methods (analyze_gap, generate_chapter_content, …)
    from MistralAIService and overrides only the low-level generate /
    generate_streaming / test_connection to call Ollama instead of Mistral.
    """

    def __init__(self, base_url: str = "http://host.docker.internal:11434",
                 model: str = "mistral:latest",
                 temperature: float = 0.3, max_tokens: int = 4096):
        # Don't call super().__init__() — we don't need a Mistral client
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def generate(
        self, system_prompt: str, user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: float = 300,
    ) -> str:
        """Generate text using Ollama HTTP API (non-streaming)."""
        input_chars = len(system_prompt) + len(user_prompt)
        effective_max = max_tokens or self.max_tokens
        logger.info("Ollama call: ~%d input chars (~%d tokens), max_output=%d, model=%s",
                     input_chars, input_chars // 4, effective_max, self.model)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature or self.temperature,
                "num_predict": effective_max,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30)) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            logger.error("Ollama call timed out after %.0fs (input ~%d chars)", timeout, input_chars)
            raise TimeoutError(f"L'appel Ollama a expiré après {timeout:.0f}s. Vérifiez que Ollama est démarré.")
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama HTTP error %s: %s", exc.response.status_code, exc.response.text[:500])
            raise RuntimeError(f"Erreur Ollama HTTP {exc.response.status_code}")
        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama at %s", self.base_url)
            raise RuntimeError(
                f"Impossible de se connecter à Ollama ({self.base_url}). "
                "Vérifiez que le serveur Ollama est démarré."
            )

        result = data.get("message", {}).get("content", "")
        logger.info("Ollama response: %d chars (~%d tokens)", len(result), len(result) // 4)
        return result

    async def generate_streaming(
        self, system_prompt: str, user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: float = 600,
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> str:
        """Generate text using Ollama streaming API."""
        import time

        input_chars = len(system_prompt) + len(user_prompt)
        effective_max = max_tokens or self.max_tokens
        logger.info("Ollama STREAM call: ~%d input chars (~%d tokens), max_output=%d, model=%s",
                     input_chars, input_chars // 4, effective_max, self.model)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "options": {
                "temperature": temperature or self.temperature,
                "num_predict": effective_max,
            },
        }

        t0 = time.monotonic()
        chunks: list[str] = []
        token_count = 0

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=60)) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if time.monotonic() - t0 > timeout:
                            logger.error("Ollama streaming timed out after %.0fs", timeout)
                            raise TimeoutError(f"L'appel Ollama a expiré après {timeout:.0f}s.")

                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        content = data.get("message", {}).get("content", "")
                        if content:
                            chunks.append(content)
                            token_count += 1

                            if on_progress and token_count % 50 == 0:
                                total_chars = sum(len(c) for c in chunks)
                                await on_progress(token_count, total_chars)

                        if data.get("done", False):
                            break

        except httpx.TimeoutException:
            logger.error("Ollama stream timed out after %.0fs", timeout)
            raise TimeoutError(f"L'appel Ollama a expiré après {timeout:.0f}s.")
        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama at %s", self.base_url)
            raise RuntimeError(
                f"Impossible de se connecter à Ollama ({self.base_url}). "
                "Vérifiez que le serveur Ollama est démarré."
            )

        result = "".join(chunks)
        elapsed = time.monotonic() - t0
        logger.info("Ollama stream done: %d tokens, %d chars in %.1fs (%.0f tok/s)",
                     token_count, len(result), elapsed,
                     token_count / elapsed if elapsed > 0 else 0)
        return result

    async def test_connection(self) -> str:
        """Test the Ollama connection."""
        return await self.generate(
            "Tu es un assistant utile.",
            "Réponds simplement 'Connexion Ollama réussie'.",
            temperature=0.1,
            timeout=30,
        )


# ── Provider factory ────────────────────────────────────────────────


def create_ai_service(config: AIConfig) -> MistralAIService:
    """Factory: create the right AI service based on provider config.

    Returns a MistralAIService (Mistral API) or OllamaAIService (local Ollama).
    Both expose the same interface (OllamaAIService inherits MistralAIService).
    """
    provider = getattr(config, "provider", "mistral") or "mistral"
    if provider == "ollama":
        base_url = getattr(config, "ollama_base_url", None) or "http://host.docker.internal:11434"
        model = getattr(config, "ollama_model", None) or "mistral:latest"
        return OllamaAIService(
            base_url=base_url,
            model=model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
    # Default: Mistral
    return MistralAIService(
        api_key=config.mistral_api_key_encrypted or "",
        model=config.model_name,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
