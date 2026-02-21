"""AI service for Mistral API integration."""
import asyncio
import json
import logging
import re
from typing import Awaitable, Callable, List, Optional, Dict

from mistralai import Mistral

from ..models.project import AIConfig

logger = logging.getLogger(__name__)


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
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        return {"summary": response, "new_requirements": [], "removed_requirements": [],
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

        response = await self.generate_streaming(
            system_prompt, user_prompt, temperature=0.2, max_tokens=12000,
            timeout=600, on_progress=on_progress,
        )
        try:
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
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
- Ne pas utiliser de formatage Markdown
- Écrire en texte brut structuré en paragraphes"""

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
- Ne pas utiliser de formatage Markdown
- Retourner uniquement le texte enrichi"""

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
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        return {"score": 0, "summary": response, "covered_requirements": [],
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
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        return {"description": "", "tags": [], "suggested_chapters": []}

    async def execute_custom_prompt(self, content: str, prompt: str, context: str = "") -> str:
        """Execute a custom user prompt on content."""
        system_prompt = """Tu es un assistant expert en rédaction de réponses aux appels d'offres.
Applique exactement l'instruction de l'utilisateur au contenu fourni.
N'utilise pas de formatage Markdown. Retourne uniquement le texte modifié."""

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
