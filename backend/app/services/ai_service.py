"""AI service for interacting with OpenAI and Mistral APIs."""
import re
from typing import List, Optional
from openai import AsyncOpenAI
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from ..models.report import AIProviderConfig, SectionStatus
from .utc_guidelines import UTC_GUIDELINES


def clean_markdown_from_text(text: str) -> str:
    """Remove markdown formatting from generated text."""
    if not text:
        return text

    # Remove bold markers ** and __
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)

    # Remove italic markers * and _
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'\1', text)

    # Remove code markers `
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Remove code blocks ```
    text = re.sub(r'```[a-z]*\n?(.*?)```', r'\1', text, flags=re.DOTALL)

    # Remove heading markers #
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove link syntax [text](url)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Remove image syntax ![alt](url)
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)

    # Clean orphaned markdown symbols
    text = re.sub(r'^\s*\*\*\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*__\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\*\s*$', '', text, flags=re.MULTILINE)

    # Remove excessive whitespace but preserve paragraph breaks
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


class AIService:
    """Service for AI-powered text generation."""

    def __init__(self, config: AIProviderConfig):
        """Initialize the AI service with the given configuration."""
        self.provider = config.provider
        self.api_key = config.api_key

        if self.provider == "openai":
            self.openai_client = AsyncOpenAI(api_key=self.api_key)
        elif self.provider == "mistral":
            self.mistral_client = MistralClient(api_key=self.api_key)
        else:
            raise ValueError(f"Unknown AI provider: {self.provider}")

    async def _generate_openai(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7
    ) -> str:
        """Generate text using OpenAI API."""
        response = await self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=4000,
        )
        return response.choices[0].message.content or ""

    def _generate_mistral(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7
    ) -> str:
        """Generate text using Mistral API."""
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        response = self.mistral_client.chat(
            model="mistral-large-latest",
            messages=messages,
            temperature=temperature,
            max_tokens=4000,
        )
        return response.choices[0].message.content or ""

    async def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.7
    ) -> str:
        """Generate text using the configured AI provider."""
        if self.provider == "openai":
            return await self._generate_openai(system_prompt, user_prompt, temperature)
        else:
            return self._generate_mistral(system_prompt, user_prompt, temperature)

    async def generate_section_content(
        self,
        section_title: str,
        section_description: str,
        notes: str,
        company_context: str,
    ) -> str:
        """Generate content for a report section based on notes."""
        system_prompt = f"""Tu es un assistant spécialisé dans la rédaction de rapports de stage universitaires.
Tu dois aider une étudiante de l'UTC (Université de Technologie de Compiègne) à rédiger son rapport de stage TN05.

{UTC_GUIDELINES}

Règles de rédaction :
- Utilise un style professionnel et académique
- Les phrases doivent être courtes, précises et riches en informations
- L'orthographe et la grammaire doivent être irréprochables
- Le niveau de langage doit être adapté à un rapport professionnel
- Évite le langage familier
- Mets en valeur les missions effectuées
- Sois cohérent avec le niveau d'une étudiante universitaire

IMPORTANT - Règles de formatage :
- N'utilise JAMAIS de formatage Markdown (pas de **, *, #, -, ```, etc.)
- Écris en texte brut uniquement
- Pour structurer le texte, utilise des paragraphes séparés par des lignes vides
- Pour les énumérations, écris simplement les éléments sur des lignes séparées sans puces ni tirets
- Le texte sera formaté automatiquement dans le document Word final"""

        user_prompt = f"""Génère le contenu pour la section suivante du rapport de stage :

Section : {section_title}
Description attendue : {section_description}

Contexte de l'entreprise :
{company_context}

Notes de l'étudiante :
{notes}

Rédige un texte professionnel et structuré pour cette section, en utilisant les notes fournies.
Le texte doit être prêt à être intégré dans le rapport final.

RAPPEL : N'utilise aucun formatage Markdown. Écris en texte brut uniquement."""

        result = await self.generate(system_prompt, user_prompt, temperature=0.6)
        return clean_markdown_from_text(result)

    async def generate_questions(
        self,
        section_title: str,
        section_description: str,
        current_notes: str = "",
        current_content: str = "",
        school_instructions: str = "",
    ) -> List[str]:
        """Generate questions to ask during the internship for a section."""
        system_prompt = f"""Tu es un assistant spécialisé dans l'accompagnement des étudiants en stage.
Tu dois aider une étudiante de l'UTC à préparer les questions à poser pendant son stage pour enrichir son rapport.

{UTC_GUIDELINES}

Ton rôle est de suggérer des questions pertinentes et professionnelles que l'étudiante peut poser
à son tuteur, ses collègues ou observer pendant son stage.

RÈGLES IMPORTANTES :
- N'utilise JAMAIS de formatage markdown (pas de **, *, #, -, etc.)
- Écris en texte brut uniquement
- Chaque question doit être unique et différente des autres
- Évite toute redondance ou répétition d'idées"""

        context_parts = []

        if current_notes:
            context_parts.append(f"""Notes actuelles de l'étudiante :
{current_notes}

Évite les questions dont les réponses sont déjà dans les notes.""")

        if current_content:
            context_parts.append(f"""Contenu déjà rédigé :
{current_content}

Évite les questions sur des sujets déjà traités dans le contenu.""")

        if school_instructions:
            context_parts.append(f"""Instructions de l'école pour le rapport :
{school_instructions}

Assure-toi que les questions aident à répondre aux exigences de l'école.""")

        context = "\n\n".join(context_parts) if context_parts else ""

        user_prompt = f"""Génère une liste de 5 à 7 questions pertinentes et UNIQUES à poser pendant le stage pour la section suivante :

Section : {section_title}
Description : {section_description}

{context}

Les questions doivent :
- Être professionnelles et adaptées au contexte d'un stage
- Permettre de récolter des informations utiles pour le rapport
- Être ouvertes pour encourager des réponses détaillées
- Couvrir différents aspects de la section
- Être TOUTES DIFFÉRENTES les unes des autres (pas de doublons ni de variations mineures)

IMPORTANT : Retourne UNIQUEMENT les questions, une par ligne, sans numérotation, sans tirets, sans formatage."""

        response = await self.generate(system_prompt, user_prompt, temperature=0.7)
        questions = [q.strip() for q in response.strip().split("\n") if q.strip()]
        # Remove duplicates while preserving order and clean formatting
        seen = set()
        unique_questions = []
        for q in questions:
            q_clean = q.lstrip("- •0123456789.)").strip()
            q_lower = q_clean.lower()
            if len(q_clean) > 10 and q_lower not in seen:
                seen.add(q_lower)
                unique_questions.append(q_clean)
        return unique_questions[:7]

    async def generate_recommendations(
        self,
        section_title: str,
        section_description: str,
        status: SectionStatus,
        current_notes: str = "",
        current_content: str = "",
        school_instructions: str = "",
    ) -> List[str]:
        """Generate recommendations for improving a section."""
        system_prompt = f"""Tu es un assistant pédagogique spécialisé dans l'accompagnement des étudiants en stage.
Tu dois aider une étudiante de l'UTC à améliorer son rapport de stage TN05.

{UTC_GUIDELINES}

Ton rôle est de donner des conseils constructifs et encourageants pour améliorer chaque section du rapport.

RÈGLES DE FORMATAGE STRICTES :
- N'utilise JAMAIS de formatage markdown (pas de **, *, #, -, etc.)
- Écris en texte brut uniquement, sans aucune mise en forme
- Chaque conseil doit être une phrase complète et claire
- Pas de listes à puces, pas de numérotation visible
- Chaque conseil doit être UNIQUE et apporter une valeur différente
- Évite les répétitions et les formulations similaires"""

        status_context = {
            SectionStatus.NOT_STARTED: "L'étudiante n'a pas encore commencé cette section.",
            SectionStatus.IN_PROGRESS: "L'étudiante travaille actuellement sur cette section.",
            SectionStatus.COMPLETED: "L'étudiante pense avoir terminé cette section.",
            SectionStatus.NEEDS_REVIEW: "Cette section nécessite une relecture.",
        }

        content_info = ""
        if current_notes:
            content_info += f"\nNotes actuelles :\n{current_notes}\n"
        if current_content:
            content_info += f"\nContenu rédigé :\n{current_content}\n"

        instructions_context = ""
        if school_instructions:
            instructions_context = f"""
Instructions officielles de l'école :
{school_instructions}

Adapte tes conseils pour aider l'étudiante à respecter ces instructions."""

        user_prompt = f"""Donne des conseils personnalisés et UNIQUES pour la section suivante :

Section : {section_title}
Description attendue : {section_description}
Statut : {status_context.get(status, "Statut inconnu")}
{content_info}
{instructions_context}

Fournis exactement 4 conseils qui sont :
- Adaptés au statut actuel et au contenu existant de la section
- Constructifs, encourageants et bienveillants
- Concrets, actionnables et spécifiques à cette section
- En lien avec les exigences UTC et les instructions de l'école
- TOUS DIFFÉRENTS les uns des autres (chaque conseil aborde un aspect différent)

IMPORTANT :
- Écris UNIQUEMENT les conseils, un par ligne
- Pas de numérotation, pas de tirets, pas de formatage
- Pas de titres en gras, pas d'astérisques
- Chaque ligne = un conseil complet et différent des autres"""

        response = await self.generate(system_prompt, user_prompt, temperature=0.7)
        recommendations = [r.strip() for r in response.strip().split("\n") if r.strip()]

        # Remove duplicates and clean formatting
        seen = set()
        unique_recs = []
        for r in recommendations:
            r_clean = r.lstrip("- •0123456789.)").strip()
            # Remove any remaining markdown
            r_clean = clean_markdown_from_text(r_clean)
            r_lower = r_clean.lower()
            if len(r_clean) > 15 and r_lower not in seen:
                seen.add(r_lower)
                unique_recs.append(r_clean)
        return unique_recs[:5]

    async def improve_text(self, text: str, section_context: str, notes: str = "") -> str:
        """Improve and proofread a text, incorporating notes if provided."""
        notes_instruction = ""
        if notes:
            notes_instruction = """
- INTÉGRANT UNIQUEMENT les informations des notes qui ne sont PAS DÉJÀ présentes dans le texte
- NE JAMAIS répéter ou dupliquer des informations déjà présentes dans le texte actuel
- Enrichissant le contenu avec SEULEMENT les détails nouveaux et pertinents des notes"""

        system_prompt = f"""Tu es un rédacteur et correcteur professionnel spécialisé dans les rapports académiques universitaires.
Tu dois améliorer le texte fourni en :
- Corrigeant toutes les fautes d'orthographe et de grammaire
- REFORMULANT de manière plus élégante et professionnelle
- Améliorant le style, la fluidité et la clarté
- Utilisant un vocabulaire riche et précis, adapté au contexte académique
- Structurant mieux les idées et les paragraphes
- Rendant le texte plus sophistiqué tout en restant accessible{notes_instruction}
- Conservant le sens et les informations originales

Le texte final doit être :
- Élégant et bien écrit
- Professionnel et académique
- Fluide et agréable à lire
- Cohérent et bien structuré

RÈGLE CRITIQUE ANTI-DUPLICATION :
- Le texte actuel contient peut-être DÉJÀ des informations issues de notes précédentes.
- Tu ne dois JAMAIS doubler ou répéter une information déjà présente dans le texte.
- Si une note contient une information déjà dans le texte, IGNORE cette note.
- Le texte résultant doit avoir une longueur similaire au texte original, sauf si de NOUVELLES informations des notes doivent être ajoutées.

IMPORTANT : N'utilise JAMAIS de formatage Markdown (pas de **, *, #, -, ```, etc.).
Retourne uniquement du texte brut sans aucune marque de formatage."""

        notes_section = ""
        if notes:
            notes_section = f"""

Notes de l'étudiante (ATTENTION : certaines de ces notes ont peut-être DÉJÀ été intégrées dans le texte actuel lors d'une amélioration précédente. N'intègre QUE les informations qui ne sont PAS ENCORE dans le texte) :
{notes}
"""

        user_prompt = f"""Améliore et reformule de manière plus élégante et professionnelle le texte suivant pour la section "{section_context}" d'un rapport de stage :{notes_section}

Texte actuel à améliorer :
{text}

RAPPEL IMPORTANT : Ne duplique AUCUNE information déjà présente dans le texte. Si les notes contiennent des infos déjà dans le texte, ne les ajoute pas une seconde fois.
Retourne uniquement le texte amélioré et reformulé, sans explications et sans aucun formatage Markdown."""

        result = await self.generate(system_prompt, user_prompt, temperature=0.4)
        return clean_markdown_from_text(result)

    async def generate_notes_from_prompt(
        self,
        section_title: str,
        section_description: str,
        user_prompt: str,
        existing_notes: str = "",
    ) -> List[str]:
        """Generate notes based on user prompt for a section."""
        system_prompt = f"""Tu es un assistant spécialisé dans l'accompagnement des étudiants en stage.
Tu aides une étudiante de l'UTC à prendre des notes pour son rapport de stage TN05.

{UTC_GUIDELINES}

Ton rôle est de générer des notes pertinentes et structurées basées sur la demande de l'utilisateur.
Les notes doivent être :
- Concises mais informatives
- Factuelles et précises
- Utiles pour la rédaction du rapport
- Adaptées au contexte professionnel d'un stage"""

        existing_context = ""
        if existing_notes:
            existing_context = f"""
Notes existantes :
{existing_notes}

Évite de répéter les informations déjà présentes dans les notes existantes."""

        prompt = f"""Génère des notes pour la section suivante du rapport de stage :

Section : {section_title}
Description : {section_description}
{existing_context}

Demande de l'utilisateur : {user_prompt}

Génère 3 à 5 notes distinctes et pertinentes basées sur cette demande.
Chaque note doit être sur une ligne séparée, sans numérotation ni puces."""

        response = await self.generate(system_prompt, prompt, temperature=0.7)
        notes = [n.strip() for n in response.strip().split("\n") if n.strip()]
        return [n.lstrip("- •0123456789.").strip() for n in notes if len(n) > 10]

    async def analyze_compliance(
        self,
        report_content: str,
        instructions_content: str,
    ) -> dict:
        """Analyze if the report complies with the given instructions."""
        system_prompt = """Tu es un expert en évaluation de rapports de stage universitaires.
Tu dois analyser si un rapport de stage respecte les instructions données.

Ton analyse doit être :
- Précise et factuelle
- Constructive
- Structurée

Tu dois identifier :
1. Les points conformes aux instructions
2. Les points non conformes ou manquants
3. Des recommandations d'amélioration

IMPORTANT : Tu dois IMPÉRATIVEMENT suivre le format de réponse exact demandé."""

        user_prompt = f"""Analyse la conformité du rapport de stage suivant par rapport aux instructions fournies.

INSTRUCTIONS DU STAGE :
{instructions_content}

CONTENU DU RAPPORT :
{report_content}

Fournis une analyse structurée avec :
1. Un score de conformité global (en pourcentage)
2. Les points conformes (liste)
3. Les points non conformes ou manquants (liste)
4. Les recommandations d'amélioration (liste)

IMPORTANT : Format ta réponse EXACTEMENT ainsi (respecte les mots-clés en majuscules) :
SCORE: [nombre entre 0 et 100]
CONFORMES:
- [point conforme 1]
- [point conforme 2]
NON_CONFORMES:
- [point non conforme 1]
- [point non conforme 2]
RECOMMANDATIONS:
- [recommandation 1]
- [recommandation 2]

N'ajoute AUCUN texte avant "SCORE:" et respecte exactement ce format."""

        response = await self.generate(system_prompt, user_prompt, temperature=0.3)

        # Log the raw response for debugging
        print("=== AI COMPLIANCE RESPONSE ===")
        print(response)
        print("=== END RESPONSE ===")

        # Parse the response with more robust parsing
        result = {
            "score": 0,
            "conformes": [],
            "non_conformes": [],
            "recommandations": []
        }

        current_section = None
        for line in response.split("\n"):
            line = line.strip()

            # Handle SCORE line with more flexibility
            if line.upper().startswith("SCORE"):
                try:
                    # Extract number from line (handles "SCORE: 75", "Score : 75%", etc.)
                    import re
                    match = re.search(r'(\d+(?:\.\d+)?)', line)
                    if match:
                        score_value = float(match.group(1))
                        result["score"] = int(score_value)
                        print(f"Parsed score: {result['score']}")
                    else:
                        print(f"Could not extract score from line: {line}")
                        result["score"] = 0
                except Exception as e:
                    print(f"Error parsing score: {e}, line: {line}")
                    result["score"] = 0

            # Handle section headers with case-insensitive matching
            elif "CONFORME" in line.upper() and line.upper().endswith(":"):
                current_section = "conformes"
                print(f"Switched to section: conformes")
            elif "NON" in line.upper() and "CONFORME" in line.upper() and line.upper().endswith(":"):
                current_section = "non_conformes"
                print(f"Switched to section: non_conformes")
            elif "RECOMMANDATION" in line.upper() and line.upper().endswith(":"):
                current_section = "recommandations"
                print(f"Switched to section: recommandations")

            # Handle bullet points
            elif line.startswith("- ") and current_section:
                item = line[2:].strip()
                if item:  # Only add non-empty items
                    result[current_section].append(item)
                    print(f"Added to {current_section}: {item[:50]}...")
            elif line.startswith("• ") and current_section:
                item = line[2:].strip()
                if item:
                    result[current_section].append(item)
                    print(f"Added to {current_section}: {item[:50]}...")

        # Log final result
        print(f"Final parsed result - Score: {result['score']}, Conformes: {len(result['conformes'])}, Non-conformes: {len(result['non_conformes'])}, Recommandations: {len(result['recommandations'])}")

        return result

    async def review_grammar_and_spelling(
        self,
        report_content: str,
    ) -> dict:
        """Review the entire report for grammar, spelling, and conjugation errors."""
        system_prompt = """Tu es un correcteur professionnel spécialisé dans les rapports académiques français.
Tu dois analyser le texte fourni et identifier TOUTES les erreurs :
- Orthographe
- Grammaire
- Conjugaison
- Ponctuation
- Syntaxe
- Style académique

Pour chaque erreur trouvée, tu dois fournir :
1. Le texte erroné exact (tel qu'il apparaît dans le document)
2. La correction proposée
3. Une brève explication de l'erreur

Sois très précis et méticuleux. N'ignore aucune erreur, même mineure."""

        user_prompt = f"""Analyse le rapport de stage suivant et identifie TOUTES les erreurs d'orthographe, de grammaire et de conjugaison :

{report_content}

IMPORTANT : Format ta réponse EXACTEMENT ainsi :

NOMBRE_ERREURS: [nombre total d'erreurs trouvées]

ERREURS:
[Pour chaque erreur, utilise ce format exact:]
---
TEXTE_ERRONE: [le texte exact contenant l'erreur]
CORRECTION: [le texte corrigé]
EXPLICATION: [explication brève de l'erreur]
---

Si aucune erreur n'est trouvée, réponds uniquement :
NOMBRE_ERREURS: 0
ERREURS:
Aucune erreur détectée. Le texte est bien rédigé sur le plan orthographique, grammatical et de conjugaison.

N'ajoute AUCUN texte avant "NOMBRE_ERREURS:" et respecte exactement ce format."""

        response = await self.generate(system_prompt, user_prompt, temperature=0.2)

        # Log the raw response for debugging
        print("=== AI GRAMMAR REVIEW RESPONSE ===")
        print(response)
        print("=== END RESPONSE ===")

        # Parse the response
        result = {
            "nombre_erreurs": 0,
            "erreurs": [],
            "message": ""
        }

        lines = response.strip().split("\n")
        i = 0

        # Parse number of errors
        while i < len(lines):
            line = lines[i].strip()
            if line.upper().startswith("NOMBRE_ERREURS"):
                try:
                    import re
                    match = re.search(r'(\d+)', line)
                    if match:
                        result["nombre_erreurs"] = int(match.group(1))
                        print(f"Parsed nombre_erreurs: {result['nombre_erreurs']}")
                except Exception as e:
                    print(f"Error parsing nombre_erreurs: {e}")
                i += 1
                break
            i += 1

        # Parse errors
        current_error = {}
        in_errors_section = False

        while i < len(lines):
            line = lines[i].strip()

            if line.upper().startswith("ERREURS:"):
                in_errors_section = True
                i += 1
                continue

            if not in_errors_section:
                i += 1
                continue

            if line == "---":
                if current_error and all(k in current_error for k in ["texte_errone", "correction", "explication"]):
                    result["erreurs"].append(current_error)
                    print(f"Added error: {current_error['texte_errone'][:50]}...")
                current_error = {}
                i += 1
                continue

            if line.upper().startswith("TEXTE_ERRONE:"):
                current_error["texte_errone"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("CORRECTION:"):
                current_error["correction"] = line.split(":", 1)[1].strip()
            elif line.upper().startswith("EXPLICATION:"):
                current_error["explication"] = line.split(":", 1)[1].strip()
            elif in_errors_section and not line.startswith("---") and line:
                # If no errors found, this might be the message
                if result["nombre_erreurs"] == 0:
                    result["message"] = line

            i += 1

        # Add last error if exists
        if current_error and all(k in current_error for k in ["texte_errone", "correction", "explication"]):
            result["erreurs"].append(current_error)

        # If no errors found, set a positive message
        if result["nombre_erreurs"] == 0 and not result["message"]:
            result["message"] = "Aucune erreur détectée. Le texte est bien rédigé sur le plan orthographique, grammatical et de conjugaison."

        print(f"Final parsed result - Nombre d'erreurs: {result['nombre_erreurs']}, Erreurs trouvées: {len(result['erreurs'])}")

        return result

    async def execute_custom_prompt(
        self,
        content: str,
        user_prompt: str,
        section_title: str,
    ) -> str:
        """Execute a custom user prompt on the content."""
        system_prompt = """Tu es un assistant spécialisé dans la rédaction de rapports de stage universitaires.
Tu dois modifier le texte fourni selon les instructions de l'utilisateur.

RÈGLES IMPORTANTES :
- Applique EXACTEMENT ce que l'utilisateur demande
- Conserve le sens général et les informations importantes du texte original
- Maintiens un style professionnel et académique
- N'utilise JAMAIS de formatage Markdown (pas de **, *, #, -, ```, etc.)
- Écris en texte brut uniquement
- Retourne UNIQUEMENT le texte modifié, sans explications ni commentaires"""

        prompt = f"""Section : {section_title}

Instruction de l'utilisateur : {user_prompt}

Texte à modifier :
{content}

Applique l'instruction de l'utilisateur au texte ci-dessus et retourne le texte modifié.
RAPPEL : N'utilise aucun formatage Markdown. Écris en texte brut uniquement."""

        result = await self.generate(system_prompt, prompt, temperature=0.5)
        return clean_markdown_from_text(result)

    async def adjust_content_length(
        self,
        content: str,
        section_title: str,
        target_pages: float,
        target_words: int,
    ) -> str:
        """Adjust the content length to match target pages."""
        current_words = len(content.split())

        if current_words > target_words:
            direction = "raccourcir"
            instruction = f"""Tu dois RACCOURCIR ce texte pour qu'il contienne environ {target_words} mots (actuellement {current_words} mots).

Pour raccourcir :
- Supprime les répétitions et redondances
- Simplifie les phrases trop longues
- Garde les informations essentielles
- Élimine les détails superflus
- Fusionne les idées similaires"""
        else:
            direction = "développer"
            instruction = f"""Tu dois DÉVELOPPER ce texte pour qu'il contienne environ {target_words} mots (actuellement {current_words} mots).

Pour développer :
- Ajoute des détails et exemples pertinents
- Développe les explications techniques
- Enrichis la description des processus
- Ajoute du contexte aux affirmations
- Approfondis l'analyse et la réflexion"""

        system_prompt = f"""Tu es un assistant spécialisé dans la rédaction de rapports de stage universitaires.
Tu dois {direction} le texte fourni pour atteindre environ {target_pages} page(s) ({target_words} mots).

{instruction}

RÈGLES IMPORTANTES :
- Le texte final doit être cohérent et fluide
- Conserve le style professionnel et académique
- Garde les informations clés et le sens général
- N'utilise JAMAIS de formatage Markdown (pas de **, *, #, -, ```, etc.)
- Écris en texte brut uniquement
- Retourne UNIQUEMENT le texte modifié, sans explications"""

        prompt = f"""Section : {section_title}

Objectif : {target_pages} page(s) (~{target_words} mots)
Actuellement : ~{current_words} mots

Texte à {direction} :
{content}

Retourne le texte ajusté pour atteindre l'objectif de longueur.
RAPPEL : N'utilise aucun formatage Markdown. Écris en texte brut uniquement."""

        result = await self.generate(system_prompt, prompt, temperature=0.5)
        return clean_markdown_from_text(result)
