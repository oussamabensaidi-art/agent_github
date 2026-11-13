---
name: twig
reviewer: code
applies: templates/*.twig
---
Twig.
- Liens générés avec `path()` / `url()`, jamais d'URL écrite à la main.
- Formulaire POST écrit à la main : champ caché `csrf_token('…')` (sinon : sécurité).
- Pas de logique métier dans le template (calculs de prime, droits) : la passer depuis le contrôleur.
- Un simple changement de texte, de libellé, d'accord ou de mise en forme n'appelle aucune remarque.
