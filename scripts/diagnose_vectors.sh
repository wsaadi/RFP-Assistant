#!/bin/bash
# ============================================================================
# Diagnostic: Inspect vector database content for table/KPI data
# Run with: bash scripts/diagnose_vectors.sh [project_name_filter]
# Example:  bash scripts/diagnose_vectors.sh "RSE"
# ============================================================================

set -euo pipefail

# Load env vars if .env exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

DB_USER="${POSTGRES_USER:-rfp_user}"
DB_NAME="${POSTGRES_DB:-rfp_assistant}"
CONTAINER="rfp-assistant-db"
PROJECT_FILTER="${1:-}"

# Helper to run psql inside the container
run_sql() {
    docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "$1"
}

echo "============================================="
echo " RFP-Assistant Vector DB Diagnostic"
echo "============================================="
echo ""

# 0. List all projects so user can identify which one to inspect
echo "=== 0. Tous les projets ==="
run_sql "
SELECT p.id, p.name, p.created_at,
       (SELECT COUNT(*) FROM documents d WHERE d.project_id = p.id) as nb_docs
FROM rfp_projects p
ORDER BY p.created_at DESC;
"

# If no filter, ask user
if [ -z "$PROJECT_FILTER" ]; then
    echo ""
    echo "💡 Pour filtrer par projet, relance avec: bash scripts/diagnose_vectors.sh \"nom_du_projet\""
    echo "   Ou utilise l'ID du projet directement."
    echo ""
    read -p "Entrez l'ID du projet (ou une partie du nom) pour continuer: " PROJECT_FILTER
fi

# Find project ID
echo ""
echo "=== Recherche du projet: '$PROJECT_FILTER' ==="
PROJECT_ID=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -c "
SELECT id FROM rfp_projects
WHERE id::text = '$PROJECT_FILTER'
   OR name ILIKE '%${PROJECT_FILTER}%'
ORDER BY created_at DESC
LIMIT 1;
")

if [ -z "$PROJECT_ID" ]; then
    echo "❌ Aucun projet trouvé pour '$PROJECT_FILTER'"
    exit 1
fi

echo "✅ Projet trouvé: $PROJECT_ID"
run_sql "SELECT id, name FROM rfp_projects WHERE id = '$PROJECT_ID';"

echo ""
echo "=== 1. Documents du projet et statut ==="
run_sql "
SELECT d.original_filename, d.category, d.processing_status, d.chunk_count, d.page_count
FROM documents d
WHERE d.project_id = '$PROJECT_ID'
ORDER BY d.category, d.created_at DESC;
"

echo ""
echo "=== 2. Embeddings par document (dans ce projet) ==="
run_sql "
SELECT de.document_name, de.category, COUNT(*) as nb_embeddings
FROM document_embeddings de
WHERE de.project_id = '$PROJECT_ID'
GROUP BY de.document_name, de.category
ORDER BY nb_embeddings DESC;
"

echo ""
echo "=== 3. Comparaison chunks vs embeddings ==="
run_sql "
SELECT d.original_filename, d.category, d.chunk_count as chunks_in_db,
       COALESCE(e.nb_embeddings, 0) as embeddings_in_vector,
       CASE WHEN d.chunk_count > 0 AND COALESCE(e.nb_embeddings, 0) = 0
            THEN '❌ MANQUANT'
            WHEN d.chunk_count > 0 AND COALESCE(e.nb_embeddings, 0) > 0
            THEN '✅ OK'
            ELSE '⚠️  VIDE'
       END as status
FROM documents d
LEFT JOIN (
    SELECT document_name, COUNT(*) as nb_embeddings
    FROM document_embeddings
    WHERE project_id = '$PROJECT_ID'
    GROUP BY document_name
) e ON d.original_filename = e.document_name
WHERE d.project_id = '$PROJECT_ID'
ORDER BY d.category, d.original_filename;
"

echo ""
echo "=== 4. Recherche 'turn over' dans les embeddings du projet ==="
run_sql "
SELECT de.document_name, de.page_number, de.chunk_index,
       LEFT(de.content, 300) as content_preview
FROM document_embeddings de
WHERE de.project_id = '$PROJECT_ID'
  AND (de.content ILIKE '%turn%over%' OR de.content ILIKE '%turnover%')
ORDER BY de.document_name, de.chunk_index;
"

echo ""
echo "=== 5. Recherche chiffres clés: 16,47 / 3,97 / 4,09 / 47782 ==="
run_sql "
SELECT de.document_name, de.page_number, de.chunk_index,
       LEFT(de.content, 300) as content_preview
FROM document_embeddings de
WHERE de.project_id = '$PROJECT_ID'
  AND (de.content ILIKE '%16,47%' OR de.content ILIKE '%16.47%'
    OR de.content ILIKE '%3,97%' OR de.content ILIKE '%3.97%'
    OR de.content ILIKE '%4,09%' OR de.content ILIKE '%4.09%'
    OR de.content ILIKE '%47782%' OR de.content ILIKE '%47 782%')
ORDER BY de.document_name, de.chunk_index;
"

echo ""
echo "=== 6. Recherche '[TABLEAU]' (extraction structurée) ==="
run_sql "
SELECT de.document_name, de.page_number, de.chunk_index,
       LEFT(de.content, 300) as content_preview
FROM document_embeddings de
WHERE de.project_id = '$PROJECT_ID'
  AND de.content ILIKE '%[TABLEAU]%'
ORDER BY de.document_name, de.chunk_index;
"

echo ""
echo "=== 7. Recherche handicap / formation dans les embeddings ==="
run_sql "
SELECT de.document_name, de.page_number, de.chunk_index,
       LEFT(de.content, 200) as content_preview
FROM document_embeddings de
WHERE de.project_id = '$PROJECT_ID'
  AND (de.content ILIKE '%handicap%'
    OR de.content ILIKE '%taux de formation%'
    OR de.content ILIKE '%heures de formation%')
ORDER BY de.document_name, de.chunk_index;
"

echo ""
echo "============================================="
echo " Diagnostic terminé"
echo "============================================="
echo ""
echo "INTERPRÉTATION:"
echo "- Section 3: Si des documents ont '❌ MANQUANT' → l'indexation vectorielle a échoué"
echo "  → Il faut re-traiter ces documents (POST /api/documents/{id}/reprocess)"
echo "- Section 4-5: Si vide → les KPIs ne sont pas dans la base vectorielle"
echo "- Section 6: Si vide → find_tables() n'était pas actif lors du traitement"
