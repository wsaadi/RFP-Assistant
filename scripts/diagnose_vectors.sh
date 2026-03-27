#!/bin/bash
# ============================================================================
# Diagnostic: Inspect vector database content for table/KPI data
# Run with: bash scripts/diagnose_vectors.sh
# ============================================================================

set -euo pipefail

# Load env vars if .env exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

DB_USER="${POSTGRES_USER:-rfp_user}"
DB_NAME="${POSTGRES_DB:-rfp_assistant}"
CONTAINER="rfp-assistant-db"

echo "============================================="
echo " RFP-Assistant Vector DB Diagnostic"
echo "============================================="
echo ""

# Helper to run psql inside the container
run_sql() {
    docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "$1"
}

# 1. Total documents and their status
echo "=== 1. Documents et statut de traitement ==="
run_sql "
SELECT d.original_filename, d.category, d.processing_status, d.chunk_count, d.page_count
FROM documents d
ORDER BY d.created_at DESC;
"

echo ""
echo "=== 2. Total embeddings par document ==="
run_sql "
SELECT de.document_name, COUNT(*) as nb_embeddings
FROM document_embeddings de
GROUP BY de.document_name
ORDER BY nb_embeddings DESC;
"

echo ""
echo "=== 3. Recherche 'turn over' dans les embeddings ==="
run_sql "
SELECT de.document_name, de.page_number, de.chunk_index,
       LEFT(de.content, 300) as content_preview
FROM document_embeddings de
WHERE de.content ILIKE '%turn%over%'
   OR de.content ILIKE '%turnover%'
ORDER BY de.document_name, de.chunk_index;
"

echo ""
echo "=== 4. Recherche 'formation professionnelle' / 'heures de formation' ==="
run_sql "
SELECT de.document_name, de.page_number, de.chunk_index,
       LEFT(de.content, 300) as content_preview
FROM document_embeddings de
WHERE de.content ILIKE '%formation professionnelle%'
   OR de.content ILIKE '%heures de formation%'
   OR de.content ILIKE '%taux de formation%'
ORDER BY de.document_name, de.chunk_index;
"

echo ""
echo "=== 5. Recherche handicap / travailleurs handicapés ==="
run_sql "
SELECT de.document_name, de.page_number, de.chunk_index,
       LEFT(de.content, 300) as content_preview
FROM document_embeddings de
WHERE de.content ILIKE '%handicap%'
   OR de.content ILIKE '%travailleurs en situation%'
ORDER BY de.document_name, de.chunk_index;
"

echo ""
echo "=== 6. Recherche de chiffres clés: 16,47 / 3,97 / 4,09 / 47782 ==="
run_sql "
SELECT de.document_name, de.page_number, de.chunk_index,
       LEFT(de.content, 300) as content_preview
FROM document_embeddings de
WHERE de.content ILIKE '%16,47%'
   OR de.content ILIKE '%16.47%'
   OR de.content ILIKE '%3,97%'
   OR de.content ILIKE '%3.97%'
   OR de.content ILIKE '%4,09%'
   OR de.content ILIKE '%4.09%'
   OR de.content ILIKE '%47782%'
   OR de.content ILIKE '%47 782%'
ORDER BY de.document_name, de.chunk_index;
"

echo ""
echo "=== 7. Recherche 'annexe' ou 'indicateur' dans les noms de documents ==="
run_sql "
SELECT de.document_name, de.page_number, de.chunk_index,
       LEFT(de.content, 400) as content_preview
FROM document_embeddings de
WHERE de.document_name ILIKE '%annexe%'
   OR de.document_name ILIKE '%indicateur%'
ORDER BY de.document_name, de.chunk_index
LIMIT 20;
"

echo ""
echo "=== 8. Recherche '[TABLEAU]' (extraction structurée de tableaux) ==="
run_sql "
SELECT de.document_name, de.page_number, de.chunk_index,
       LEFT(de.content, 400) as content_preview
FROM document_embeddings de
WHERE de.content ILIKE '%[TABLEAU]%'
ORDER BY de.document_name, de.chunk_index;
"

echo ""
echo "=== 9. Chunks du document contenant 'Annexe' (premiers 10) ==="
run_sql "
SELECT dc.document_id, d.original_filename, dc.page_number, dc.chunk_index,
       LEFT(dc.content, 400) as content_preview
FROM document_chunks dc
JOIN documents d ON dc.document_id = d.id
WHERE d.original_filename ILIKE '%annexe%'
   OR d.original_filename ILIKE '%indicateur%'
ORDER BY dc.chunk_index
LIMIT 10;
"

echo ""
echo "============================================="
echo " Diagnostic terminé"
echo "============================================="
echo ""
echo "INTERPRÉTATION:"
echo "- Si section 3-6 sont vides → les données numériques ne sont PAS dans la base vectorielle"
echo "- Si section 8 est vide → l'extraction de tableaux (find_tables) n'a PAS été utilisée"
echo "  → Les documents doivent être re-traités avec le nouveau code"
echo "- Si section 7/9 sont vides → le document Annexe 1 n'a pas été uploadé/indexé"
echo ""
echo "SOLUTION: Utilisez l'endpoint POST /api/documents/{doc_id}/reprocess"
echo "pour forcer le re-traitement avec la nouvelle extraction de tableaux."
