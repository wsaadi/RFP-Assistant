"""Service for generating soutenance (defense) preparation materials using AI."""
import logging

from .ai_service import _parse_json_object

logger = logging.getLogger(__name__)


def _parse_json_response(raw: str) -> dict:
    """Parse JSON from AI response, with truncation repair support."""
    result = _parse_json_object(raw)
    if result is not None:
        return result
    raise ValueError("L'IA n'a pas retourne un JSON valide pour la soutenance")


SOUTENANCE_SYSTEM_PROMPT = """Tu es un expert en preparation de soutenances commerciales pour les appels d'offres.

Tu recois le contenu complet d'une reponse a un appel d'offres (chapitres avec leurs contenus).
Tu dois generer un plan de soutenance complet et professionnel.

Tu dois retourner un JSON valide avec cette structure EXACTE:

{
  "sections": [
    {
      "title": "Titre de la section",
      "duration": "X min",
      "slides": [
        {
          "title": "Titre du slide",
          "subtitle": "Sous-titre optionnel",
          "bullets": ["Point 1", "Point 2", "Point 3"],
          "speaker_notes": "Notes detaillees pour le presentateur: ce qu'il doit dire, les points cles a aborder, les transitions..."
        }
      ]
    }
  ],
  "key_figures": [
    {"value": "XX%", "label": "Description du chiffre"}
  ],
  "strengths": [
    "Force 1 de notre proposition",
    "Force 2 de notre proposition"
  ],
  "script": {
    "total_duration": "XX minutes",
    "introduction": "Script detaille de l'introduction: comment ouvrir la soutenance, presenter l'equipe, le contexte...",
    "sections": [
      {
        "title": "Titre de la section",
        "duration": "X min",
        "presenter_guide": "Guide detaille pour le presentateur: les points a aborder dans l'ordre, les elements cles a mettre en avant, les exemples concrets a donner, les transitions vers la section suivante...",
        "key_messages": ["Message cle 1", "Message cle 2"],
        "anticipated_questions": ["Question possible 1", "Question possible 2"],
        "suggested_answers": ["Reponse suggeree 1", "Reponse suggeree 2"]
      }
    ],
    "closing": "Script de conclusion: resume des points forts, appel a l'action, formule de cloture...",
    "qa_preparation": {
      "expected_questions": [
        {
          "question": "Question anticipee",
          "answer": "Reponse recommandee detaillee",
          "tips": "Conseils pour repondre de maniere convaincante"
        }
      ],
      "difficult_topics": [
        {
          "topic": "Sujet delicat",
          "strategy": "Comment aborder ce point de maniere positive"
        }
      ]
    },
    "general_tips": [
      "Conseil pratique 1 pour la soutenance",
      "Conseil pratique 2"
    ]
  }
}

REGLES IMPORTANTES:
1. La soutenance doit suivre un deroulement logique et persuasif pour une presentation de 45 a 60 minutes
2. Commence par le contexte et la comprehension du besoin du client
3. Presente ensuite la solution proposee, la methodologie, les moyens, l'equipe, le planning
4. Termine par les forces differenciantes et la conclusion
5. Le script doit etre TRES detaille et actionnable - c'est un vrai guide de preparation
6. Anticipe les questions difficiles du jury (au moins 8-10 questions)
7. Mets en avant les elements differenciants par rapport a la concurrence
8. Les speaker_notes doivent contenir ce que le presentateur doit DIRE mot pour mot
9. IMPORTANT: Genere environ {slide_count} slides de contenu au total (hors slides de titre et de transition). Chaque section doit avoir entre 3 et 8 slides. Repartis bien les slides entre les sections pour couvrir l'ensemble de la presentation
10. Chaque slide doit avoir 3 a 5 bullet points detailles
11. Chaque section doit avoir une duree estimee
12. Les key_figures doivent etre des chiffres extraits du contenu (pas inventes) - au moins 4 chiffres
13. Les strengths doivent refleter les vrais points forts de la proposition - au moins 6 forces
14. NE PAS inventer de chiffres, statistiques ou references qui ne sont pas dans le contenu
15. Utiliser [A COMPLETER] pour les informations manquantes
16. Decoupe bien les sections: Contexte/Comprehension, Solution proposee, Methodologie/Approche, Equipe/Moyens, Planning/Livrables, Retour d'experience/References, Engagement qualite, Valeur ajoutee
17. Chaque section des anticipated_questions doit avoir au moins 2-3 questions"""


def build_soutenance_prompt(
    project_name: str,
    client_name: str,
    company_name: str,
    rfp_reference: str,
    chapters_data: list,
    ai_context: str = "",
    slide_count: int = 35,
) -> tuple:
    """Build the system and user prompts for soutenance generation.

    Returns (system_prompt, user_prompt).
    """
    system = SOUTENANCE_SYSTEM_PROMPT.replace("{slide_count}", str(slide_count))

    if company_name and client_name:
        system += f"""

## CONTEXTE
- Soumissionnaire: {company_name}
- Client: {client_name}
- La soutenance est presentee PAR {company_name} AU client {client_name}
"""

    if ai_context:
        system += f"""

## CONTEXTE ADDITIONNEL DE REDACTION
{ai_context}
"""

    # Build chapters text
    chapters_text_parts = []
    for ch in chapters_data:
        numbering = ch.get("numbering", "")
        title = ch.get("title", "")
        content = ch.get("content", "")
        chapter_type = ch.get("chapter_type", "chapter")

        if content and content.strip():
            # Truncate very long chapters to avoid token limits
            truncated = content[:5000] if len(content) > 5000 else content
            suffix = "... [contenu tronque]" if len(content) > 5000 else ""
            chapters_text_parts.append(
                f"### {numbering} {title} ({chapter_type})\n{truncated}{suffix}"
            )
        else:
            chapters_text_parts.append(f"### {numbering} {title} ({chapter_type})\n[Pas de contenu]")

        # Include children
        for child in ch.get("children", []):
            c_content = child.get("content", "")
            c_numbering = child.get("numbering", "")
            c_title = child.get("title", "")
            if c_content and c_content.strip():
                truncated = c_content[:3000] if len(c_content) > 3000 else c_content
                suffix = "... [contenu tronque]" if len(c_content) > 3000 else ""
                chapters_text_parts.append(
                    f"#### {c_numbering} {c_title}\n{truncated}{suffix}"
                )

    chapters_text = "\n\n".join(chapters_text_parts)

    user = f"""Voici la reponse a l'appel d'offres pour laquelle tu dois preparer la soutenance:

**Projet:** {project_name}
**Client:** {client_name}
**Soumissionnaire:** {company_name}
**Reference AO:** {rfp_reference}

---

CONTENU DE LA REPONSE:

{chapters_text}

---

Genere le JSON complet pour la preparation de la soutenance. Sois tres detaille dans le script et les notes du presentateur."""

    return system, user
