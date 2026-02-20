"""AI service for Mistral API integration."""
import asyncio
import json
import re
from typing import List, Optional, Dict

from mistralai import Mistral

from ..models.project import AIConfig


class MistralAIService:
    """Service for AI-powered operations using Mistral API."""

    def __init__(self, api_key: str, model: str = "mistral-large-latest",
                 temperature: float = 0.3, max_tokens: int = 4096):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

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
    ) -> str:
        """Generate text using Mistral API (native async)."""
        async with Mistral(api_key=self.api_key) as client:
            response = await client.chat.complete_async(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            )
        return response.choices[0].message.content or ""

    async def test_connection(self) -> str:
        """Test the API connection."""
        return await self.generate(
            "Tu es un assistant utile.",
            "Réponds simplement 'Connexion Mistral réussie'.",
            temperature=0.1,
        )

    async def analyze_gap(
        self, old_rfp_content: str, new_rfp_content: str
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
{old_rfp_content[:15000]}

NOUVEL APPEL D'OFFRES:
{new_rfp_content[:15000]}

Analyse les écarts entre ces deux appels d'offres."""

        response = await self.generate(system_prompt, user_prompt, temperature=0.2, max_tokens=8000)
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        return {"summary": response, "new_requirements": [], "removed_requirements": [],
                "modified_requirements": [], "unchanged_requirements": []}

    async def generate_response_structure(
        self, rfp_content: str, old_response_structure: str = ""
    ) -> List[Dict]:
        """Generate the complete response structure from the RFP requirements."""
        system_prompt = """Tu es un expert en réponse aux appels d'offres.
À partir du contenu d'un appel d'offres, génère la structure complète de la réponse.

La structure doit inclure:
- Chapitres principaux
- Sous-chapitres
- Annexes requises
- Documents à fournir

Réponds au format JSON (sans markdown):
[
  {
    "title": "...",
    "description": "...",
    "chapter_type": "chapter|sub_chapter|annexe|document_to_provide",
    "rfp_requirement": "exigence originale de l'AO",
    "children": [
      {
        "title": "...",
        "description": "...",
        "chapter_type": "sub_chapter",
        "rfp_requirement": "...",
        "children": []
      }
    ]
  }
]"""

        context = ""
        if old_response_structure:
            context = f"\n\nSTRUCTURE DE L'ANCIENNE RÉPONSE (pour référence):\n{old_response_structure}"

        user_prompt = f"""APPEL D'OFFRES:
{rfp_content[:15000]}
{context}

Génère la structure complète de la réponse à cet appel d'offres."""

        response = await self.generate(system_prompt, user_prompt, temperature=0.2, max_tokens=8000)
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
