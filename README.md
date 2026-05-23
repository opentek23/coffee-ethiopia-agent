# Coffee Ethiopia — Agent de prospection

Scraping automatique toutes les heures via GitHub Actions.  
**Un seul outil nécessaire : ta clé API Anthropic.**  
Pas de SerpAPI, pas de compte tiers, rien d'autre.

## Comment ça marche

Claude utilise son outil `web_search` intégré pour chercher sur le web,
puis extrait directement les entreprises éthiopiennes du café.
Les résultats s'accumulent dans `data/companies_master.csv`.

## Mise en place (5 minutes)

### Étape 1 — Créer le repo GitHub
- Va sur [github.com](https://github.com) → bouton **New repository**
- Nom : `coffee-ethiopia-agent` (ou ce que tu veux)
- Visibilité : **Private** recommandé
- Cliquer **Create repository**

### Étape 2 — Uploader les fichiers
Dans ton nouveau repo, clique **Add file → Upload files** et glisse :
```
agent.py
requirements.txt
README.md
.github/workflows/scrape.yml
```

### Étape 3 — Ajouter le secret API
Dans ton repo :
**Settings → Secrets and variables → Actions → New repository secret**

| Nom du secret | Valeur |
|---|---|
| `ANTHROPIC_API_KEY` | Ta clé depuis console.anthropic.com |

### Étape 4 — Autoriser l'écriture
**Settings → Actions → General → Workflow permissions**  
→ Sélectionner **Read and write permissions** → Save

### Étape 5 — Lancer le premier test
**Actions → Coffee Ethiopia — Scraping 24h → Run workflow → Run workflow**

Après ~3 minutes, va dans **Code → data/** pour voir le CSV.

## Résultat

Deux fichiers CSV dans le dossier `data/` :

| Fichier | Contenu |
|---|---|
| `companies_master.csv` | Toutes les entreprises depuis le début (cumulatif) |
| `companies_latest.csv` | Résultats du dernier run |

Colonnes : `company_name`, `city`, `email`, `phone`, `website`, `first_seen`

## Coût estimé

| Service | Coût |
|---|---|
| GitHub Actions | Gratuit (2 000 min/mois inclus) |
| Anthropic API (24 runs) | ~$1–2 pour 24h complètes |
