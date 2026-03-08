# Documents de test pour le load test

Placez vos vrais documents (PDF, DOCX, XLSX) dans les sous-dossiers
par categorie. Chaque utilisateur simule uploade **tous** les fichiers
de chaque categorie.

```
documents_test/
├── new_rfp/          # Le nouvel appel d'offres (obligatoire, 1+ fichiers)
├── old_rfp/          # L'ancien AO (optionnel)
├── old_response/     # L'ancienne reponse (optionnel)
└── inspiration/      # Docs d'inspiration (optionnel)
```

Formats supportes : `.pdf`, `.docx`, `.xlsx`, `.doc`, `.xls`

Le load test ignorera les dossiers vides. Si `new_rfp/` est vide,
le test utilisera les fixtures generees par defaut.
