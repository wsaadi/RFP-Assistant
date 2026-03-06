"""Prompt moderation service for RFP Assistant.

Validates user-provided text inputs (custom prompts, AI context, notes,
improvement axes) to ensure they stay within the professional scope of
an RFP response tool.  Rejects insults, illegal content, off-topic
requests, and other inappropriate inputs.
"""
import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# ── Category: Insults & profanity (FR + EN) ──────────────────────────

_PROFANITY_PATTERNS = [
    # French insults / vulgarities
    re.compile(r"\b(?:put(?:e|ain)|merde|connard|connasse|encul[eé]|salaud|salope|bordel|ta\s+gueule|ferme[\s-]la|nique|niqu[eé]|batard|bâtard|pd|fdp|ntm|tg)\b", re.IGNORECASE),
    re.compile(r"\b(?:fils\s+de\s+pute|va\s+te\s+faire|je\s+t['\u2019]emmerde|casse[\s-]toi)\b", re.IGNORECASE),
    # English insults / vulgarities
    re.compile(r"\b(?:fuck(?:ing|ed|er|off)?|shit(?:ty)?|bitch|asshole|bastard|dick(?:head)?|cunt|stfu|gtfo|motherfucker)\b", re.IGNORECASE),
]

# ── Category: Hate speech, discrimination, threats ───────────────────

_HATE_SPEECH_PATTERNS = [
    re.compile(r"\b(?:racaille|sous-race|sous[\s-]homme|nègre|négro|bougnoule|youpin|bicot|sale\s+(?:arabe|juif|noir|blanc|gay))\b", re.IGNORECASE),
    re.compile(r"\b(?:je\s+vais\s+(?:te|vous|les?)\s+(?:tuer|buter|crever|dégommer|exploser|éliminer))\b", re.IGNORECASE),
    re.compile(r"\b(?:i['\u2019]ll\s+kill|death\s+threat|gonna\s+(?:kill|murder|shoot))\b", re.IGNORECASE),
]

# ── Category: Illegal activity requests ──────────────────────────────

_ILLEGAL_PATTERNS = [
    re.compile(r"\b(?:pirater|hacker|ddos|exploit(?:er)?\s+une?\s+faille|voler\s+des?\s+donn[eé]es|phishing)\b", re.IGNORECASE),
    re.compile(r"\b(?:fabriquer\s+(?:une?\s+)?(?:bombe|explosif|drogue)|blanchiment|corruption|pot[\s-]de[\s-]vin)\b", re.IGNORECASE),
    re.compile(r"\b(?:how\s+to\s+(?:hack|steal|make\s+a\s+bomb|launder\s+money))\b", re.IGNORECASE),
]

# ── Category: Off-topic / non-professional ───────────────────────────

_OFF_TOPIC_PATTERNS = [
    # Attempts to use the AI for personal/non-RFP tasks
    re.compile(r"\b(?:écris[\s-]moi\s+(?:un[e]?\s+)?(?:po[eè]me|chanson|blague|histoire\s+(?:d['\u2019]amour|érotique|drôle)|lettre\s+d['\u2019]amour|rap|slam))\b", re.IGNORECASE),
    re.compile(r"\b(?:write\s+(?:me\s+)?(?:a\s+)?(?:poem|song|joke|love\s+(?:letter|story)|rap|erotic|fan\s*fiction))\b", re.IGNORECASE),
    re.compile(r"\b(?:raconte[\s-]moi\s+(?:une?\s+)?(?:blague|histoire\s+drôle))\b", re.IGNORECASE),
    # Sexual / adult content
    re.compile(r"\b(?:porno(?:graphi(?:e|que))?|sexuel(?:lement)?|contenu\s+(?:adulte|érotique)|nude|xxx)\b", re.IGNORECASE),
]

# ── Mapping of pattern categories to rejection reasons ───────────────

_CATEGORY_CHECKS = [
    (_PROFANITY_PATTERNS, "insult", "Le texte contient des insultes ou un langage vulgaire. Merci de reformuler de manière professionnelle."),
    (_HATE_SPEECH_PATTERNS, "hate_speech", "Le texte contient des propos haineux, discriminatoires ou menaçants. Ce type de contenu n'est pas accepté."),
    (_ILLEGAL_PATTERNS, "illegal", "Le texte fait référence à des activités illégales. Ce type de contenu n'est pas accepté dans le cadre d'un appel d'offres."),
    (_OFF_TOPIC_PATTERNS, "off_topic", "Le texte est hors sujet du cadre professionnel d'un appel d'offres. Merci de reformuler votre demande en lien avec la rédaction RFP."),
]


class ModerationResult:
    """Result of a moderation check."""

    __slots__ = ("is_allowed", "category", "message")

    def __init__(self, is_allowed: bool, category: str = "", message: str = ""):
        self.is_allowed = is_allowed
        self.category = category
        self.message = message

    def __bool__(self) -> bool:
        return self.is_allowed


_ALLOWED = ModerationResult(is_allowed=True)


def moderate_prompt(text: str, field_name: str = "input") -> ModerationResult:
    """Check user-provided text for inappropriate content.

    Returns a ModerationResult.  When ``is_allowed`` is False the caller
    should reject the request and return ``message`` to the user.

    This is a synchronous, regex-based check designed to be fast and to
    run without any external API call.
    """
    if not text or not text.strip():
        return _ALLOWED

    for patterns, category, message in _CATEGORY_CHECKS:
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                logger.warning(
                    "Prompt moderation BLOCKED [%s] in field '%s': "
                    "matched '%s' in text '%.120s...'",
                    category, field_name, match.group(), text,
                )
                return ModerationResult(
                    is_allowed=False,
                    category=category,
                    message=message,
                )

    return _ALLOWED
