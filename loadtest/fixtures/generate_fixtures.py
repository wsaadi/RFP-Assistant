#!/usr/bin/env python3
"""Generate realistic sample documents for load testing."""
import os

DIR = os.path.dirname(os.path.abspath(__file__))


def generate_sample_pdf(path: str, title: str, pages: int = 3):
    """Generate a minimal valid PDF with text content."""
    lines = []
    lines.append("%PDF-1.4")

    # Build pages
    page_objects = []
    content_objects = []
    obj_id = 5  # reserve 1-4 for catalog, pages, font, procset

    for i in range(pages):
        content_id = obj_id
        page_id = obj_id + 1
        obj_id += 2

        text = f"Page {i+1} - {title}\\n"
        text += f"Appel d offres pour la fourniture de services informatiques.\\n"
        text += f"Le prestataire devra demontrer sa capacite a fournir des solutions innovantes.\\n"
        text += f"Criteres d evaluation : expertise technique, references clients, prix.\\n"
        text += f"Date limite de soumission : 15 mars 2026.\\n"
        text += f"Budget estimatif : 500 000 EUR HT.\\n"

        stream = f"BT /F1 12 Tf 50 750 Td ({text}) Tj ET"
        content_objects.append((content_id, stream))
        page_objects.append((page_id, content_id))

    # Write objects
    objects = {}
    # Catalog
    objects[1] = "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj"
    # Pages
    kids = " ".join(f"{pid} 0 R" for (pid, _) in page_objects)
    objects[2] = f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {pages} >>\nendobj"
    # Font
    objects[3] = "3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj"
    # ProcSet
    objects[4] = "4 0 obj\n[/PDF /Text]\nendobj"

    for cid, stream in content_objects:
        objects[cid] = f"{cid} 0 obj\n<< /Length {len(stream)} >>\nstream\n{stream}\nendstream\nendobj"

    for pid, cid in page_objects:
        objects[pid] = (
            f"{pid} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 612 792] "
            f"/Contents {cid} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> /ProcSet 4 0 R >> "
            f">>\nendobj"
        )

    body = ""
    offsets = {}
    for oid in sorted(objects.keys()):
        offsets[oid] = len(body.encode("latin-1")) + len("%PDF-1.4\n")
        body += objects[oid] + "\n"

    xref_offset = len("%PDF-1.4\n".encode("latin-1")) + len(body.encode("latin-1"))
    xref = f"xref\n0 {max(objects.keys()) + 1}\n"
    xref += "0000000000 65535 f \n"
    for oid in range(1, max(objects.keys()) + 1):
        if oid in offsets:
            xref += f"{offsets[oid]:010d} 00000 n \n"
        else:
            xref += "0000000000 00000 f \n"

    trailer = (
        f"trailer\n<< /Size {max(objects.keys()) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    )

    with open(path, "wb") as f:
        f.write(b"%PDF-1.4\n")
        f.write(body.encode("latin-1"))
        f.write(xref.encode("latin-1"))
        f.write(trailer.encode("latin-1"))


def generate_sample_docx(path: str, title: str):
    """Generate a minimal valid DOCX (ZIP-based) with text content."""
    import zipfile
    import xml.etree.ElementTree as ET

    W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

    paragraphs_text = [
        title,
        "1. Objet du marche",
        "Le present appel d'offres a pour objet la selection d'un prestataire pour la mise en oeuvre d'une solution de gestion documentaire integree.",
        "2. Contexte et enjeux",
        "Notre organisation souhaite moderniser ses processus de gestion documentaire afin d'ameliorer l'efficacite operationnelle.",
        "3. Perimetre de la prestation",
        "Le prestataire devra fournir : analyse des besoins, conception de la solution, developpement, integration, formation des utilisateurs, et maintenance.",
        "4. Criteres d'evaluation",
        "Les offres seront evaluees selon : qualite technique (40%), references (20%), prix (30%), delais (10%).",
        "5. Calendrier previsionnel",
        "Phase 1 : Cadrage - 2 mois. Phase 2 : Realisation - 6 mois. Phase 3 : Deploiement - 2 mois.",
        "6. Budget",
        "Le budget previsionnel est de 350 000 EUR HT, hors frais de maintenance annuelle.",
    ]

    # Build document.xml
    doc = ET.Element(f"{{{W_NS}}}document")
    body = ET.SubElement(doc, f"{{{W_NS}}}body")
    for text in paragraphs_text:
        p = ET.SubElement(body, f"{{{W_NS}}}p")
        r = ET.SubElement(p, f"{{{W_NS}}}r")
        t = ET.SubElement(r, f"{{{W_NS}}}t")
        t.text = text

    doc_xml = ET.tostring(doc, encoding="unicode", xml_declaration=True)

    # Build [Content_Types].xml
    types = ET.Element("Types", xmlns=CT_NS)
    ET.SubElement(types, "Default", Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
    ET.SubElement(types, "Default", Extension="xml", ContentType="application/xml")
    ET.SubElement(types, "Override", PartName="/word/document.xml",
                  ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
    ct_xml = ET.tostring(types, encoding="unicode", xml_declaration=True)

    # Build _rels/.rels
    rels_root = ET.Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
    ET.SubElement(rels_root, "Relationship", Id="rId1", Type=R_NS.replace("officeDocument/2006/relationships", "officeDocument/2006/relationships/officeDocument"), Target="word/document.xml")
    rels_xml = ET.tostring(rels_root, encoding="unicode", xml_declaration=True)

    # Build word/_rels/document.xml.rels (empty)
    doc_rels = ET.Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
    doc_rels_xml = ET.tostring(doc_rels, encoding="unicode", xml_declaration=True)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", ct_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("word/document.xml", doc_xml)
        zf.writestr("word/_rels/document.xml.rels", doc_rels_xml)


def main():
    # RFP documents
    generate_sample_pdf(
        os.path.join(DIR, "sample_rfp.pdf"),
        "Appel d'Offres - Modernisation SI",
        pages=5,
    )
    generate_sample_pdf(
        os.path.join(DIR, "sample_old_rfp.pdf"),
        "Ancien AO - Transformation Digitale",
        pages=3,
    )
    generate_sample_docx(
        os.path.join(DIR, "sample_response.docx"),
        "Reponse Technique - Projet SI",
    )
    generate_sample_docx(
        os.path.join(DIR, "sample_old_response.docx"),
        "Ancienne Reponse - Projet Digital",
    )
    print(f"Fixtures generated in {DIR}")


if __name__ == "__main__":
    main()
