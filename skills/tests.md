---
name: tests
reviewer: code
applies: src/*.php, tests/*.php
---
Tests.
- Nouvelle logique métier (service, calcul, règle, nouvelle méthode publique) sans test dans la PR → major.
  Ne le signale pas si la PR ajoute ou modifie un test qui couvre ce code.
- Correctif de bug sans test qui reproduit le bug → major.
- Ne juge pas les valeurs attendues d'un test existant sauf erreur évidente.
- Un ajout de test, de documentation, de style (CSS) ou un renommage sans changement de comportement n'appelle aucune remarque.
- Typage : ne signale un type manquant que si le paramètre ou le retour n'a vraiment aucun type dans le diff.
