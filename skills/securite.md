---
name: securite
reviewer: securite
applies: *.php, *.twig, *.yaml, *.yml, *.js
---
Sécurité web PHP / Symfony (OWASP). Signale seulement une faille réelle dans les lignes ajoutées.
- Injection : SQL ou DQL construite en concaténant une donnée externe (`$request`, paramètre de méthode) → critical. `find()`, `findBy()`, `setParameter()`, paramètres liés : sûrs.
- XSS : Twig échappe par défaut ; danger = `|raw` ou `autoescape false` sur une donnée saisie.
- Contrôle d'accès : une action qui MODIFIE ou SUPPRIME des données sans rôle adapté (`#[IsGranted]`, voter, `denyAccessUnlessGranted`). Un `#[IsGranted]` posé sur la CLASSE s'applique à toutes ses méthodes : ne le redemande pas. Un rôle abaissé (ex. `ROLE_GESTIONNAIRE` → `ROLE_USER`) sur une action d'écriture est une faille.
- CSRF : formulaire POST écrit à la main sans `csrf_token()`, ou `isCsrfTokenValid` supprimé. Les formulaires du composant Form sont protégés par défaut.
- Redirection ouverte : `redirect()` vers une URL venant de la requête.
- Désérialisation : `unserialize()` sur une entrée externe → critical. Préférer `json_decode`.
- Signatures / jetons comparés avec `==` ou `===` au lieu de `hash_equals()`.
- Fichiers : nom client (`getClientOriginalName`) utilisé dans un chemin ; upload sans contrôle du type.
- Requêtes sortantes vers une URL fournie par l'utilisateur (SSRF).
- Données personnelles (nom, SIREN, IBAN, email) écrites dans les logs.
- Secrets : déjà détectés par un autre outil ; ne les recommente pas.
