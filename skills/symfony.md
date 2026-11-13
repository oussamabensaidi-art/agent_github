---
name: symfony
reviewer: code
applies: src/*.php, config/*.yaml, config/*.yml
---
Symfony 7 : bonnes pratiques et pièges courants.
- Injection de dépendances par le constructeur ; une propriété promue (`private readonly X $x` dans `__construct`) EST injectée : `$this->x` est valide. Signale seulement `$this->container->get()` ou un `new` de service.
- Un argument de contrôleur typé entité (`Contract $contract`) est résolu par Symfony : 404 automatique si absent. Ne demande pas de vérifier son existence.
- Formulaire : traiter seulement si `isSubmitted() && isValid()` ; rediriger après un POST réussi.
- Contrôleurs minces : la logique métier va dans un service testé.
- Les routes (`#[Route]` sur la classe) préfixent celles des méthodes.
- `$request->query->getString()` / `getInt()` plutôt que `get()` sans type.
- Pas de `dump()`, `dd()`, `var_dump()`, `print_r()` laissés → major.
- Exceptions : jamais de `catch` vide ; ne pas afficher un succès si l'enregistrement a échoué.
- Montants : entiers en centimes ; un calcul en flottant ou un `(int)` qui tronque au lieu d'arrondir → major.
