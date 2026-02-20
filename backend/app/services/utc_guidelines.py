"""UTC TN05 internship report guidelines and default structure."""
from typing import List
from ..models.report import ReportSection, ReportPlan, SectionStatus

# Complete UTC TN05 Guidelines
UTC_GUIDELINES = """
# Consignes UTC pour le rapport de stage TN05

## Objectifs du stage
Le stage ouvrier ou d'exécutant se déroule en bac+1 ou bac+2 de la formation d'ingénieur.
Il s'agit d'un premier contact avec la vie professionnelle permettant d'appréhender
la dimension humaine et organisationnelle du futur métier d'ingénieur.

## Compétences visées
- Appliquer des techniques de recherche de stage
- S'intégrer dans un contexte professionnel nouveau
- Mettre en perspective le rôle de l'ingénieur
- Assimiler des connaissances pratiques et prendre du recul
- Valoriser les activités réalisées et les compétences acquises

## Structure du rapport (10-20 pages hors annexes)
1. Page de garde (1 page)
2. Remerciements (1 page)
3. Sommaire (1-2 pages)
4. Introduction (1 page)
5. Présentation de la société
6. Organisation du travail et/ou de la production
7. Tâches accomplies durant le stage
8. Bilan et réflexion (1-2 pages)
9. Analyse d'une situation perçue (1-2 pages)
10. Conclusion (1 page)
11. Annexes / bibliographie (facultatives)

## Éléments de la page de garde
- Nom (majuscule), prénom (minuscule) et semestre en haut à droite
- Logo UTC en haut à gauche
- Dates du stage
- Nom de la société (+ photo/logo)
- Lieu du stage (ville + département)
- Nom du tuteur entreprise en bas à gauche

## Mise en forme
- Marges raisonnables
- Pagination à partir de l'introduction
- Parties et sections numérotées
- Illustrations avec titres et numéros
- Termes techniques définis en bas de page ou glossaire
- Sources référencées en bibliographie
- Impression recto/verso possible, relié avec feuille plastique

## Style de rédaction
- Phrases courtes, précises, riches en informations
- Police traditionnelle (taille 12 corps, 14 titres)
- Orthographe et grammaire irréprochables
- Langage professionnel adapté
"""


def get_default_report_plan() -> ReportPlan:
    """Generate the default UTC TN05 report plan structure."""
    sections: List[ReportSection] = [
        ReportSection(
            id="cover_page",
            title="Page de garde",
            description="Page de couverture avec les informations essentielles : nom, prénom, semestre, logo UTC, dates du stage, nom et logo de l'entreprise, lieu du stage, nom du tuteur.",
            required=True,
            order=1,
            min_pages=1,
            max_pages=1,
            status=SectionStatus.NOT_STARTED,
        ),
        ReportSection(
            id="acknowledgments",
            title="Remerciements",
            description="Remerciements adressés aux principaux acteurs du stage : tuteur entreprise, équipe, collègues, et toute personne ayant contribué à la réussite du stage.",
            required=True,
            order=2,
            min_pages=1,
            max_pages=1,
            status=SectionStatus.NOT_STARTED,
        ),
        ReportSection(
            id="table_of_contents",
            title="Sommaire",
            description="Plan détaillé du rapport avec numérotation des parties et pagination.",
            required=True,
            order=3,
            min_pages=1,
            max_pages=2,
            status=SectionStatus.NOT_STARTED,
        ),
        ReportSection(
            id="introduction",
            title="Introduction",
            description="Présentation du contexte du stage, des motivations, de l'intérêt du stage et annonce du plan du rapport.",
            required=True,
            order=4,
            min_pages=1,
            max_pages=1,
            status=SectionStatus.NOT_STARTED,
            subsections=[
                ReportSection(
                    id="intro_context",
                    title="Contexte et motivations",
                    description="Expliquer pourquoi ce stage, comment il a été trouvé, les attentes initiales.",
                    required=True,
                    order=1,
                    parent_id="introduction",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="intro_objectives",
                    title="Objectifs du stage",
                    description="Présenter les objectifs personnels et professionnels du stage.",
                    required=True,
                    order=2,
                    parent_id="introduction",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="intro_plan",
                    title="Annonce du plan",
                    description="Présenter brièvement le plan du rapport.",
                    required=True,
                    order=3,
                    parent_id="introduction",
                    status=SectionStatus.NOT_STARTED,
                ),
            ],
        ),
        ReportSection(
            id="company_presentation",
            title="Présentation de la société",
            description="Description complète de l'entreprise : historique, organisation, secteur d'activité, clients, fournisseurs, concurrents, chiffres clés, partenaires sociaux.",
            required=True,
            order=5,
            min_pages=2,
            max_pages=4,
            status=SectionStatus.NOT_STARTED,
            subsections=[
                ReportSection(
                    id="company_history",
                    title="Historique et identité",
                    description="Date de création, fondateurs, évolution de l'entreprise, valeurs, culture d'entreprise.",
                    required=True,
                    order=1,
                    parent_id="company_presentation",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="company_sector",
                    title="Secteur d'activité",
                    description="Domaine d'activité, produits ou services proposés, marché cible.",
                    required=True,
                    order=2,
                    parent_id="company_presentation",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="company_organization",
                    title="Organisation et structure",
                    description="Organigramme, différents services, effectifs, implantations géographiques.",
                    required=True,
                    order=3,
                    parent_id="company_presentation",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="company_market",
                    title="Environnement économique",
                    description="Principaux clients et fournisseurs, concurrents, chiffres clés (CA, parts de marché).",
                    required=True,
                    order=4,
                    parent_id="company_presentation",
                    status=SectionStatus.NOT_STARTED,
                ),
            ],
        ),
        ReportSection(
            id="work_organization",
            title="Organisation du travail",
            description="Description de l'organisation du travail et/ou de la production : horaires, cadences, sécurité, conditions de travail.",
            required=True,
            order=6,
            min_pages=1,
            max_pages=2,
            status=SectionStatus.NOT_STARTED,
            subsections=[
                ReportSection(
                    id="work_schedule",
                    title="Horaires et rythme de travail",
                    description="Planning, horaires, pauses, flexibilité.",
                    required=True,
                    order=1,
                    parent_id="work_organization",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="work_conditions",
                    title="Conditions de travail",
                    description="Environnement de travail, équipements, ambiance.",
                    required=True,
                    order=2,
                    parent_id="work_organization",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="work_safety",
                    title="Sécurité",
                    description="Règles de sécurité, équipements de protection, formations sécurité.",
                    required=True,
                    order=3,
                    parent_id="work_organization",
                    status=SectionStatus.NOT_STARTED,
                ),
            ],
        ),
        ReportSection(
            id="tasks_accomplished",
            title="Tâches accomplies durant le stage",
            description="Description précise mais synthétisée des missions : contexte, objectif, rôle/apport, problématique rencontrée, synthèse/valeur ajoutée.",
            required=True,
            order=7,
            min_pages=3,
            max_pages=5,
            status=SectionStatus.NOT_STARTED,
            subsections=[
                ReportSection(
                    id="tasks_main",
                    title="Missions principales",
                    description="Description détaillée des tâches principales confiées.",
                    required=True,
                    order=1,
                    parent_id="tasks_accomplished",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="tasks_secondary",
                    title="Missions secondaires",
                    description="Autres tâches réalisées pendant le stage.",
                    required=False,
                    order=2,
                    parent_id="tasks_accomplished",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="tasks_challenges",
                    title="Difficultés rencontrées et solutions",
                    description="Problèmes rencontrés et comment ils ont été résolus.",
                    required=True,
                    order=3,
                    parent_id="tasks_accomplished",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="tasks_results",
                    title="Résultats et valeur ajoutée",
                    description="Bilan des réalisations et apport pour l'entreprise.",
                    required=True,
                    order=4,
                    parent_id="tasks_accomplished",
                    status=SectionStatus.NOT_STARTED,
                ),
            ],
        ),
        ReportSection(
            id="reflection",
            title="Bilan et réflexion",
            description="Réflexion personnelle sur les relations humaines, le métier et le rôle de l'ingénieur, l'organisation du travail.",
            required=True,
            order=8,
            min_pages=1,
            max_pages=2,
            status=SectionStatus.NOT_STARTED,
            subsections=[
                ReportSection(
                    id="reflection_human",
                    title="Relations humaines",
                    description="Analyse des interactions avec les collègues, la hiérarchie, l'équipe.",
                    required=True,
                    order=1,
                    parent_id="reflection",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="reflection_engineer",
                    title="Le rôle de l'ingénieur",
                    description="Réflexion sur la place et le rôle de l'ingénieur observé dans l'entreprise.",
                    required=True,
                    order=2,
                    parent_id="reflection",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="reflection_skills",
                    title="Compétences acquises",
                    description="Nouvelles compétences techniques et humaines développées.",
                    required=True,
                    order=3,
                    parent_id="reflection",
                    status=SectionStatus.NOT_STARTED,
                ),
            ],
        ),
        ReportSection(
            id="situation_analysis",
            title="Analyse d'une situation perçue",
            description="Analyse approfondie d'une situation vécue pendant le stage avec réflexion personnelle.",
            required=True,
            order=9,
            min_pages=1,
            max_pages=2,
            status=SectionStatus.NOT_STARTED,
            subsections=[
                ReportSection(
                    id="analysis_skills_perception",
                    title="Compétences pour le futur métier",
                    description="Comment percevez-vous les compétences à mobiliser pour votre futur métier ?",
                    required=False,
                    order=1,
                    parent_id="situation_analysis",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="analysis_knowledge",
                    title="Savoir, savoir-faire, savoir-être",
                    description="Comment percevez-vous les enjeux du savoir, du savoir-faire et du savoir-être ?",
                    required=False,
                    order=2,
                    parent_id="situation_analysis",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="analysis_surprise",
                    title="Ce qui vous a étonné",
                    description="Qu'est-ce qui vous a le plus étonné dans l'entreprise ? Points forts surprenants, points faibles inattendus.",
                    required=False,
                    order=3,
                    parent_id="situation_analysis",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="analysis_relationships",
                    title="Relations interpersonnelles",
                    description="Dans les relations interpersonnelles, qu'est-ce qui vous a étonné ?",
                    required=False,
                    order=4,
                    parent_id="situation_analysis",
                    status=SectionStatus.NOT_STARTED,
                ),
            ],
        ),
        ReportSection(
            id="conclusion",
            title="Conclusion",
            description="Synthèse du stage, apports professionnels et personnels, perspectives pour la suite de la formation et le projet professionnel.",
            required=True,
            order=10,
            min_pages=1,
            max_pages=1,
            status=SectionStatus.NOT_STARTED,
            subsections=[
                ReportSection(
                    id="conclusion_summary",
                    title="Synthèse de l'expérience",
                    description="Résumé des points clés du stage.",
                    required=True,
                    order=1,
                    parent_id="conclusion",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="conclusion_benefits",
                    title="Apports du stage",
                    description="Ce que le stage a apporté sur le plan professionnel et personnel.",
                    required=True,
                    order=2,
                    parent_id="conclusion",
                    status=SectionStatus.NOT_STARTED,
                ),
                ReportSection(
                    id="conclusion_future",
                    title="Perspectives",
                    description="Impact sur le projet professionnel et la suite de la formation.",
                    required=True,
                    order=3,
                    parent_id="conclusion",
                    status=SectionStatus.NOT_STARTED,
                ),
            ],
        ),
        ReportSection(
            id="annexes",
            title="Annexes et bibliographie",
            description="Documents complémentaires, références, calculs, exemples de réalisations, copies d'écran. Les annexes doivent être titrées, numérotées et répertoriées.",
            required=False,
            order=11,
            status=SectionStatus.NOT_STARTED,
        ),
    ]

    return ReportPlan(sections=sections, total_min_pages=10, total_max_pages=20)
