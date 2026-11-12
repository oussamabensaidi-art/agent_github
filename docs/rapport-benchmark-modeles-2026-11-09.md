# Rapport de test — Comparaison des modèles pour l'agent de revue des PR

**Date :** 9 novembre 2026 · **Auteur :** Oussama Bensaidi · **Projet :** Agent IA de revue des Pull Requests

## 1. Conclusion

**Qwen3-14B offre le meilleur rapport qualité / matériel sur notre banc de test.**
Il trouve presque autant de défauts que Qwen3-Coder-Next, produit peu de bruit et
tourne déjà sur notre GPU de 20 Go.

- **Qwen3-Coder-Next** est le plus performant : seul modèle à détecter le contrôle
  d'accès manquant à chaque passage, classé « bloquant ». Mais il signale à tort un
  problème d'arrondi sur la PR saine à chaque passage, et il exige un GPU de 80 à 96 Go.
- **Qwen3-Coder-30B-A3B** ne justifie pas sa mémoire supplémentaire : il n'a jamais
  trouvé le contrôle d'accès et ajoute des remarques sur la PR saine.
- **Qwen2.5-Coder-7B** (référence du prototype) est nettement en dessous.

L'échantillon est très petit (4 PR fictives, 3 passages par modèle) : c'est une
première orientation, pas le benchmark de 30 à 50 PR demandé.

## 2. Ce qui a été testé

| Configuration | Hébergement | Quantification / fournisseur |
|---|---|---|
| Qwen2.5-Coder-7B | Ollama local, CPU (8 vCPU, 8 Go) | Q4 Ollama — test du 5 novembre |
| Qwen3-14B `/chat` | API LLM Calipso (`188.40.58.26:8085`) | AWQ 4 bits |
| Qwen3-14B `/think` | API LLM Calipso | AWQ 4 bits |
| Qwen3-Coder-Next | OpenRouter | Parasail |
| Qwen3-Coder-30B-A3B-Instruct | OpenRouter | SiliconFlow, Amazon Bedrock |
| Qwen3-14B | OpenRouter | DeepInfra, NextBit |

**Non testés :** Qwen2.5-Coder-14B-AWQ et DeepSeek-Coder-V2-Lite ne sont pas
disponibles sur OpenRouter et ne tiennent pas dans la mémoire du poste de test.

**Paramètres communs :** température 0,1 ; schéma JSON imposé dans le prompt ;
mêmes règles d'équipe ; une analyse à la fois (pas de charge simultanée).

## 3. Banc de test

Le banc exécute le vrai agent (API, worker, Redis) avec un faux GitHub et une boîte
mail de test. **Seul du code fictif a été envoyé aux modèles.**

| PR | Contenu | Attendu d'un bon relecteur |
|---|---|---|
| #101 | Contrôleur Symfony de suppression de contrat, clé AWS en dur | Injection SQL (bloquant), `dump()` oublié, route sans contrôle d'accès ; la clé est traitée par le détecteur de secrets |
| #102 | Service de calcul de prime, propre, avec son test | Aucune remarque |
| #103 | Fichier de 2 000 lignes + le même service sans test | Fichier trop volumineux signalé ; test manquant (règle d'équipe) |
| #104 | Webhook sur un ancien commit | Ignoré |

Tous les contrôles indépendants du modèle passent pour toutes les configurations :
statut de la PR, email d'alerte, secret jamais divulgué, doublons et commits
obsolètes ignorés.

## 4. Résultats

### Détection des défauts (3 passages par modèle sauf mention)

| Défaut | 2.5-Coder-7B ¹ | Qwen3-14B Calipso `/chat` | Qwen3-14B Calipso `/think` | Coder-Next | Coder-30B-A3B | Qwen3-14B OpenRouter |
|---|---|---|---|---|---|---|
| Injection SQL (#101) | trouvée, « majeur » | 3/3 bloquant | 3/3 bloquant | 3/3 bloquant | 3/3 bloquant | 3/3 bloquant |
| `dump()` oublié (#101) | trouvé | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| **Contrôle d'accès manquant (#101)** | **0** | **1/3** | **1/3** | **3/3 bloquant** | **0/3** | **2/3** |
| Test manquant (#103, 1 passage) | non | trouvé | trouvé | non | non | trouvé |

¹ 2 passages sur #101, le 5 novembre.

### Bruit et fiabilité

| | 2.5-Coder-7B | Calipso `/chat` | Calipso `/think` | Coder-Next | Coder-30B-A3B | Qwen3-14B OpenRouter |
|---|---|---|---|---|---|---|
| Remarques sur la PR saine (#102) | 1 inutile | aucune (3/3) | aucune (1 seul passage abouti) | 1 à chaque passage (arrondi) | 2, dans 2 passages sur 3 | 1, dans 1 passage sur 3 |
| Verdict de la PR saine | prête | prête 3/3 | prête 1/3, incomplète 2/3 | à vérifier 3/3 | à vérifier 2/3 | prête 2/3 |
| Remarques pertinentes ² | ≈ 2 sur 5 | 8 / 8 | 8 / 8 | 9 / 12 | 6 / 10 | 9 / 10 |
| Échecs d'appel | 0 | 0 / 7 | 2 / 7 (502, coupure) | 0 ³ | 0 | 0 |

² Remarques du modèle uniquement (hors détecteur de secrets). Les remarques sur
l'arrondi de #102 sont comptées comme non pertinentes : le code est correct, même si
l'usage de flottants pour des montants est un vrai sujet pour un assureur.

³ Après ajout d'une reprise sur l'erreur 429 : le fournisseur unique de Coder-Next
(Parasail) était temporairement saturé au premier essai.

### Temps de réponse par PR

| Configuration | Durée |
|---|---|
| Qwen2.5-Coder-7B (CPU local) | 40 à 215 s |
| Qwen3-14B Calipso `/chat` | 17 à 40 s |
| Qwen3-14B Calipso `/think` | 19 à 76 s (reprises comprises) |
| Coder-Next (OpenRouter) | 5 à 22 s |
| Coder-30B-A3B (OpenRouter) | 1 à 18 s |
| Qwen3-14B (OpenRouter) | 7 à 15 s |

Les durées OpenRouter reflètent le matériel de ces fournisseurs : elles ne disent
rien de ce que donnera notre GPU.

**Coût OpenRouter de la série complète :** environ 0,006 $ (moins de 0,001 $ par PR).

## 5. Mise en regard du dimensionnement

Chiffres fournis par l'équipe infra :

| Candidat | Poids | GPU pour le pilote | Résultat sur le banc |
|---|---|---|---|
| Qwen3-14B-AWQ (existant) | 9,4 Go | 32 à 48 Go (tourne sur 20 Go actuels) | Très bon ; contrôle d'accès 1 à 2 fois sur 3 |
| Qwen2.5-Coder-14B-AWQ | ≈ 10 Go | 48 Go | Non testé |
| DeepSeek-Coder-V2-Lite | ≈ 10 Go | 20 Go | Non testé (compatibilité vLLM à vérifier) |
| Qwen2.5-Coder-7B-AWQ | ≈ 5,5 Go | 20 Go | Insuffisant |
| Qwen3-Coder-30B-A3B | ≈ 17 Go | 32 Go minimum, 48 Go confortable | En dessous du 14B |
| Qwen3-Coder-Next | 40 à 49 Go | 80 à 96 Go | Le meilleur, mais bruyant sur la PR saine |

## 6. Limites du test

- **Échantillon réduit :** 4 PR fictives, 3 passages. Les écarts de 1 sur 3 ne sont
  pas significatifs.
- **Quantifications différentes :** OpenRouter ne sert pas la version AWQ 4 bits de
  notre serveur. On ne peut pas encore attribuer à l'AWQ l'écart sur le contrôle
  d'accès (1/3 sur notre serveur, 2/3 sur OpenRouter).
- **Pas de mesure de charge** ni de consommation mémoire.
- **Le modèle ne voit que le diff :** le contrôle d'accès manqué est probablement lié
  à l'absence de contexte (routes, configuration de sécurité), à confirmer.
- **API Calipso en HTTP non chiffré** sur une IP publique : à corriger avant tout
  essai sur du code réel.
- **OpenRouter est un service externe :** utilisé uniquement avec du code fictif,
  fournisseurs qui conservent ou entraînent sur les données exclus.

## 7. Recommandations

1. **Retenir Qwen3-14B (`/chat`) comme modèle de référence du pilote**, sur le GPU actuel.
2. **Ajouter le contexte au modèle** (routes, configuration de sécurité, fonctions
   liées, tests) et rejouer #101 comme premier cas de non-régression sur le contrôle
   d'accès.
3. **Construire le benchmark de 30 à 50 PR étiquetées** (changements sains, défauts
   connus, cas de droits d'accès) avec 1 à 2 relecteurs, et y comparer Qwen3-14B-AWQ,
   Qwen2.5-Coder-14B-AWQ et DeepSeek-Coder-V2-Lite sur notre propre serveur.
4. **Ne pas acheter de GPU de 80 à 96 Go pour Coder-Next à ce stade :** son avantage
   sur ce banc se limite au contrôle d'accès, que le contexte peut peut-être apporter
   au 14B.
5. **Mesurer sous charge** (p95 attente comprise, analyses simultanées, mémoire)
   avant de dimensionner le GPU du pilote.
6. **Passer l'API LLM Calipso en HTTPS** ou sur un réseau privé.
