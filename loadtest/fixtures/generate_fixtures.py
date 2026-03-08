#!/usr/bin/env python3
"""Generate realistic sample documents for load testing.

PDFs are generated with fpdf2 to ensure proper text extraction.
Each document contains enough content (>20 words per page) to produce
valid chunks during document processing.
"""
import os

DIR = os.path.dirname(os.path.abspath(__file__))

# ── Realistic content blocks ──

NEW_RFP_CONTENT = """APPEL D'OFFRES - MODERNISATION DU SYSTEME D'INFORMATION

1. OBJET DU MARCHE

Le present appel d'offres a pour objet la selection d'un prestataire pour la conception, le developpement et le deploiement d'une solution de modernisation du systeme d'information de notre organisation. Cette modernisation couvre l'ensemble des processus metier, depuis la gestion documentaire jusqu'au pilotage strategique.

Le prestataire retenu devra demontrer une expertise avancee dans les technologies cloud, les architectures microservices et les methodologies agiles. Il devra egalement garantir la conformite aux normes de securite en vigueur, notamment le RGPD et la norme ISO 27001.

2. CONTEXTE ET ENJEUX

Notre organisation emploie 2500 collaborateurs repartis sur 15 sites en France. Le systeme d'information actuel, base sur des technologies legacy (mainframe COBOL, bases Oracle 11g), ne repond plus aux besoins d'agilite et de performance requis par nos activites. Les principaux enjeux sont les suivants :

- Reduction des couts d'exploitation de 30% sur 3 ans
- Amelioration de la disponibilite des services (objectif 99.9%)
- Acceleration du time-to-market pour les nouveaux produits
- Mise en conformite reglementaire complete
- Amelioration de l'experience utilisateur interne et externe

3. PERIMETRE DE LA PRESTATION

3.1 Lot 1 : Audit et cadrage strategique
Le prestataire realisera un audit complet du SI existant comprenant la cartographie applicative, l'analyse des flux de donnees, l'evaluation de la dette technique et la definition de la trajectoire de transformation. Cette phase inclut egalement la redaction du schema directeur SI sur 5 ans.

3.2 Lot 2 : Conception et architecture
La conception de la nouvelle architecture devra s'appuyer sur les principes suivants : architecture orientee services, containerisation avec Kubernetes, API Gateway pour l'exposition des services, event-driven architecture pour les flux temps reel. Le prestataire proposera une architecture de reference documentee.

3.3 Lot 3 : Developpement et integration
Le developpement sera realise en methodologie agile (Scrum) avec des sprints de 2 semaines. Le prestataire mettra en place une chaine CI/CD complete incluant les tests automatises, l'analyse de code statique et le deploiement continu. Les technologies privilegiees sont Python, React, PostgreSQL et Redis.

3.4 Lot 4 : Migration des donnees
La migration des donnees depuis les systemes legacy vers la nouvelle plateforme devra etre realisee sans interruption de service. Le prestataire proposera une strategie de migration progressive avec validation par lot et mecanisme de rollback.

3.5 Lot 5 : Formation et conduite du changement
Le prestataire assurera la formation de 200 utilisateurs cles et la mise en place d'un dispositif d'accompagnement au changement incluant des ambassadeurs internes, une documentation utilisateur complete et un support de niveau 1 pendant 6 mois.

4. CRITERES D'EVALUATION

Les offres seront evaluees selon les criteres suivants :
- Qualite technique de la solution proposee : 40%
- References et experience sur des projets similaires : 20%
- Prix global de la prestation : 25%
- Respect du calendrier et des engagements de qualite : 15%

5. CALENDRIER PREVISIONNEL

Phase 1 : Audit et cadrage - 3 mois (T1 2026)
Phase 2 : Conception et architecture - 4 mois (T2-T3 2026)
Phase 3 : Developpement - 12 mois (T3 2026 - T3 2027)
Phase 4 : Migration et deploiement - 6 mois (T3-T4 2027)
Phase 5 : Stabilisation et transfert - 3 mois (T1 2028)

6. BUDGET ESTIMATIF

Le budget estimatif pour l'ensemble de la prestation est de 2 500 000 EUR HT, reparti comme suit :
- Lot 1 : 150 000 EUR HT
- Lot 2 : 300 000 EUR HT
- Lot 3 : 1 200 000 EUR HT
- Lot 4 : 400 000 EUR HT
- Lot 5 : 450 000 EUR HT

7. MODALITES DE REPONSE

Les candidats devront soumettre leur offre avant le 30 avril 2026. Le dossier de reponse comprendra un memoire technique detaille, un planning de realisation, les CV des intervenants cles et une proposition financiere decomposee par lot. Les offres seront evaluees par un comite de selection compose de la DSI, de la direction generale et d'un expert externe independant.
"""

OLD_RFP_CONTENT = """ANCIEN APPEL D'OFFRES - TRANSFORMATION DIGITALE

1. OBJET

Le marche porte sur la transformation digitale des processus metier de l'organisation. Il comprend la mise en place d'outils collaboratifs, la digitalisation des parcours clients et l'optimisation des processus internes grace aux technologies numeriques.

2. CONTEXTE

L'organisation compte 2000 collaborateurs et souhaite accelerer sa transformation digitale. Le SI actuel repose sur des technologies vieillissantes necessitant une modernisation progressive pour repondre aux nouveaux usages.

3. PRESTATIONS ATTENDUES

3.1 Mise en place d'une plateforme collaborative (Microsoft 365 ou equivalent)
3.2 Deploiement d'un CRM pour la gestion de la relation client
3.3 Digitalisation des processus RH (recrutement, formation, evaluation)
3.4 Mise en place d'un portail client self-service
3.5 Formation des equipes aux nouveaux outils

4. CRITERES D'ATTRIBUTION

- Valeur technique : 50%
- Prix : 30%
- Delais : 20%

5. BUDGET

Budget maximal : 800 000 EUR HT sur 24 mois.

6. CALENDRIER

Demarrage prevu : septembre 2024. Duree : 18 mois. La phase de recette interviendra au T2 2025 avec une mise en production progressive par lot fonctionnel.
"""

RESPONSE_CONTENT = [
    "REPONSE TECHNIQUE - PROJET DE MODERNISATION SI",
    "",
    "1. PRESENTATION DE NOTRE SOCIETE",
    "",
    "Notre societe est un acteur majeur du conseil et de l'integration de systemes d'information, "
    "avec plus de 15 ans d'experience dans la transformation digitale des grandes organisations. "
    "Nous comptons 500 consultants specialises repartis sur 8 agences en France et intervenons "
    "aupres de plus de 200 clients dans les secteurs public et prive.",
    "",
    "2. COMPREHENSION DU BESOIN",
    "",
    "Nous avons analyse en detail votre appel d'offres et identifie les enjeux majeurs suivants : "
    "la necessite de moderniser un SI legacy tout en garantissant la continuite de service, "
    "l'importance d'une approche progressive pour limiter les risques, et le besoin d'accompagner "
    "les utilisateurs dans cette transformation. Notre proposition s'articule autour de ces trois axes.",
    "",
    "3. APPROCHE TECHNIQUE",
    "",
    "Nous proposons une architecture cloud-native basee sur Kubernetes, avec une approche "
    "microservices permettant une scalabilite horizontale et une resilience accrue. Les composants "
    "principaux incluent un API Gateway Kong, un bus evenementiel Kafka, une base PostgreSQL "
    "pour les donnees transactionnelles et Elasticsearch pour la recherche full-text.",
    "",
    "4. METHODOLOGIE",
    "",
    "Notre methodologie s'appuie sur le framework SAFe adapte a votre contexte. Nous constituerons "
    "un Agile Release Train de 4 equipes Scrum travaillant en sprints de 2 semaines avec des "
    "Program Increments de 10 semaines. Cette organisation garantit une livraison continue de "
    "valeur tout en maintenant une vision d'ensemble coherente.",
    "",
    "5. PLANNING DETAILLE",
    "",
    "Sprint 0 (S1-S2) : mise en place de l'environnement, CI/CD, conventions de code. "
    "PI 1 (S3-S12) : socle technique, authentification, gestion documentaire de base. "
    "PI 2 (S13-S22) : modules metier principaux, integration avec les systemes legacy. "
    "PI 3 (S23-S32) : migration des donnees, portail utilisateur, reporting. "
    "PI 4 (S33-S42) : optimisation, securite avancee, deploiement progressif.",
    "",
    "6. EQUIPE PROPOSEE",
    "",
    "L'equipe sera composee de : 1 directeur de projet (20 ans d'experience), 1 architecte "
    "technique senior, 4 tech leads, 12 developpeurs full-stack, 2 experts DevOps, "
    "2 consultants fonctionnels, 1 expert securite et 1 chef de projet conduite du changement. "
    "L'ensemble des intervenants sont certifies (AWS, Kubernetes, Scrum).",
]

OLD_RESPONSE_CONTENT = [
    "ANCIENNE REPONSE TECHNIQUE - PROJET DE TRANSFORMATION DIGITALE",
    "",
    "1. CONTEXTE DE NOTRE INTERVENTION",
    "",
    "Suite a votre consultation, nous avons le plaisir de vous presenter notre proposition "
    "pour l'accompagnement de votre transformation digitale. Notre equipe possede une expertise "
    "reconnue dans la mise en oeuvre de solutions Microsoft 365, Salesforce et les outils "
    "de digitalisation des processus RH.",
    "",
    "2. SOLUTION PROPOSEE",
    "",
    "Nous proposons une approche en trois phases : diagnostic des usages actuels, conception "
    "de la solution cible integrant Microsoft 365 comme socle collaboratif et Salesforce comme "
    "CRM, puis deploiement progressif par direction. Cette approche permet de valider chaque "
    "etape avant de passer a la suivante et de limiter les risques de regression.",
    "",
    "3. LIVRABLES PRINCIPAUX",
    "",
    "Les livrables incluent : le rapport d'audit initial, le dossier d'architecture technique, "
    "les specifications fonctionnelles detaillees, les manuels utilisateur, le plan de formation "
    "et le dossier de recette. Chaque livrable sera soumis a validation avant passage a l'etape "
    "suivante conformement a notre methodologie qualite certifiee ISO 9001.",
    "",
    "4. PROPOSITION FINANCIERE",
    "",
    "Notre proposition financiere s'eleve a 750 000 EUR HT decomposee comme suit : "
    "phase de diagnostic 80 000 EUR, phase de conception 120 000 EUR, phase de realisation "
    "400 000 EUR, phase de deploiement et formation 150 000 EUR. Ce montant inclut la "
    "garantie de 12 mois post-mise en production.",
]


def generate_sample_pdf(path: str, content: str):
    """Generate a valid PDF with text content using raw PDF operators.

    Splits content into pages of ~2000 chars each, wrapping long lines.
    Uses standard PDF text operators so text extractors can read it.
    """
    # Split content into pages (~2000 chars each for readable pages)
    paragraphs = [p.strip() for p in content.strip().split("\n") if p.strip()]
    pages_text: list[list[str]] = []
    current_page: list[str] = []
    current_len = 0
    for para in paragraphs:
        # Wrap long paragraphs at ~80 chars
        words = para.split()
        lines: list[str] = []
        line: list[str] = []
        for w in words:
            if sum(len(x) for x in line) + len(line) + len(w) > 80:
                lines.append(" ".join(line))
                line = [w]
            else:
                line.append(w)
        if line:
            lines.append(" ".join(line))

        for ln in lines:
            if current_len + len(ln) > 2000 and current_page:
                pages_text.append(current_page)
                current_page = []
                current_len = 0
            current_page.append(ln)
            current_len += len(ln)
        # Add blank line between paragraphs
        current_page.append("")
        current_len += 1

    if current_page:
        pages_text.append(current_page)

    # Build PDF objects
    objects: dict[int, str] = {}
    # Object 1: Catalog
    objects[1] = "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj"
    # Object 3: Font
    objects[3] = "3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj"

    page_obj_ids: list[int] = []
    next_id = 4

    for page_lines in pages_text:
        content_id = next_id
        page_id = next_id + 1
        next_id += 2

        # Build text stream — escape special PDF chars
        stream_lines = ["BT", "/F1 11 Tf", "50 750 Td", "14 TL"]
        for ln in page_lines:
            # Escape backslashes and parentheses for PDF strings
            safe = ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_lines.append(f"({safe}) '")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines)

        objects[content_id] = (
            f"{content_id} 0 obj\n"
            f"<< /Length {len(stream)} >>\n"
            f"stream\n{stream}\nendstream\n"
            f"endobj"
        )
        objects[page_id] = (
            f"{page_id} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 612 792] "
            f"/Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> "
            f">>\nendobj"
        )
        page_obj_ids.append(page_id)

    # Object 2: Pages
    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects[2] = f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(page_obj_ids)} >>\nendobj"

    # Serialize
    header = b"%PDF-1.4\n"
    body = b""
    offsets: dict[int, int] = {}
    for oid in sorted(objects.keys()):
        offsets[oid] = len(header) + len(body)
        body += (objects[oid] + "\n").encode("latin-1", errors="replace")

    xref_offset = len(header) + len(body)
    max_id = max(objects.keys())
    xref = f"xref\n0 {max_id + 1}\n"
    xref += "0000000000 65535 f \n"
    for oid in range(1, max_id + 1):
        if oid in offsets:
            xref += f"{offsets[oid]:010d} 00000 n \n"
        else:
            xref += "0000000000 00000 f \n"

    trailer = (
        f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    )

    with open(path, "wb") as f:
        f.write(header)
        f.write(body)
        f.write(xref.encode("latin-1"))
        f.write(trailer.encode("latin-1"))


def generate_sample_docx(path: str, paragraphs: list[str]):
    """Generate a minimal valid DOCX (ZIP-based) with text content."""
    import zipfile
    import xml.etree.ElementTree as ET

    W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

    # Build document.xml
    doc = ET.Element(f"{{{W_NS}}}document")
    body = ET.SubElement(doc, f"{{{W_NS}}}body")
    for text in paragraphs:
        p = ET.SubElement(body, f"{{{W_NS}}}p")
        r = ET.SubElement(p, f"{{{W_NS}}}r")
        t = ET.SubElement(r, f"{{{W_NS}}}t")
        t.text = text

    doc_xml = ET.tostring(doc, encoding="unicode", xml_declaration=True)

    # Build [Content_Types].xml
    types = ET.Element("Types", xmlns=CT_NS)
    ET.SubElement(types, "Default", Extension="rels",
                  ContentType="application/vnd.openxmlformats-package.relationships+xml")
    ET.SubElement(types, "Default", Extension="xml", ContentType="application/xml")
    ET.SubElement(types, "Override", PartName="/word/document.xml",
                  ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
    ct_xml = ET.tostring(types, encoding="unicode", xml_declaration=True)

    # Build _rels/.rels
    rels_root = ET.Element("Relationships",
                           xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
    ET.SubElement(rels_root, "Relationship", Id="rId1",
                  Type=R_NS.replace("officeDocument/2006/relationships",
                                    "officeDocument/2006/relationships/officeDocument"),
                  Target="word/document.xml")
    rels_xml = ET.tostring(rels_root, encoding="unicode", xml_declaration=True)

    # Build word/_rels/document.xml.rels (empty)
    doc_rels = ET.Element("Relationships",
                          xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
    doc_rels_xml = ET.tostring(doc_rels, encoding="unicode", xml_declaration=True)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", ct_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("word/document.xml", doc_xml)
        zf.writestr("word/_rels/document.xml.rels", doc_rels_xml)


def main():
    generate_sample_pdf(
        os.path.join(DIR, "sample_rfp.pdf"),
        NEW_RFP_CONTENT,
    )
    generate_sample_pdf(
        os.path.join(DIR, "sample_old_rfp.pdf"),
        OLD_RFP_CONTENT,
    )
    generate_sample_docx(
        os.path.join(DIR, "sample_response.docx"),
        RESPONSE_CONTENT,
    )
    generate_sample_docx(
        os.path.join(DIR, "sample_old_response.docx"),
        OLD_RESPONSE_CONTENT,
    )

    # Print stats
    for name in ["sample_rfp.pdf", "sample_old_rfp.pdf", "sample_response.docx", "sample_old_response.docx"]:
        path = os.path.join(DIR, name)
        size = os.path.getsize(path)
        print(f"  {name}: {size:,} bytes")
    print(f"\nFixtures generated in {DIR}")


if __name__ == "__main__":
    main()
