# Documents de test pour le load test

Placez vos documents réels (PDF, DOCX, DOC, XLSX, XLS, PPTX) dans les sous-dossiers
par catégorie. Chaque utilisateur simulé uploade **tous** les fichiers
de chaque catégorie.

```
documents_test/
├── new_rfp/          # Le nouvel appel d'offres (obligatoire, 1+ fichiers)
├── old_rfp/          # L'ancien appel d'offres (optionnel)
├── old_response/     # L'ancienne réponse (optionnel)
└── inspiration/      # Documents d'inspiration (optionnel)
```

## Formats supportés

`.pdf`, `.docx`, `.doc`, `.xlsx`, `.xls`, `.pptx`

Taille maximale par fichier : **100 Mo**.

## Comportement

- Le load test ignore les dossiers vides.
- Si `new_rfp/` est vide, le test utilise les fixtures générées par défaut.
- Les fichiers sont validés par magic bytes (le contenu doit correspondre à l'extension).
