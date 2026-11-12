<?php

// Règles de style de l'agent (le .php-cs-fixer.php du dépôt n'est jamais chargé :
// c'est du PHP, donc du code de la PR).
return (new PhpCsFixer\Config())
    ->setRiskyAllowed(false)
    ->setRules(['@Symfony' => true])
    ->setUsingCache(false);
