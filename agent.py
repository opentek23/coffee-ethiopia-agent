"""
Agent prospection café Éthiopie
Outil utilisé : web_search intégré à l'API Anthropic (aucun service tiers)
Résultat     : data/companies_master.csv  (cumulatif, enrichi à chaque run)
               data/companies_latest.csv  (résultats du run en cours)
"""

import os, csv, json, hashlib, re
from datetime import datetime
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY    = os.environ["ANTHROPIC_API_KEY"]
RUN_NUM    = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
NOW        = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
DATA_DIR   = "data"
MASTER_CSV = f"{DATA_DIR}/companies_master.csv"
LATEST_CSV = f"{DATA_DIR}/companies_latest.csv"
FIELDS     = ["company_name", "city", "email", "phone", "website", "first_seen"]

# ── 8 angles de recherche en rotation ─────────────────────────────────────────
BATCHES = [
    # 0 — export général
    [
        "Ethiopian coffee export companies with email and phone contact Addis Ababa",
        "Ethiopia coffee trading company contact details email address",
    ],
    # 1 — régions Sidama / Yirgacheffe
    [
        "Sidama coffee company Ethiopia contact email phone number",
        "Yirgacheffe coffee producer exporter Ethiopia email",
    ],
    # 2 — région Jimma / Kaffa
    [
        "Jimma coffee company Ethiopia contact phone email",
        "Kaffa forest coffee Ethiopia exporter contact",
    ],
    # 3 — coopératives
    [
        "Ethiopian coffee farmers cooperative union email contact",
        "Oromia coffee cooperative Ethiopia phone number",
    ],
    # 4 — torréfacteurs
    [
        "coffee roaster Ethiopia specialty coffee company email",
        "Ethiopian coffee roasting company contact details",
    ],
    # 5 — emballage / packaging
    [
        "coffee packaging supplier Ethiopia company contact email",
        "Ethiopia coffee bag manufacturer phone email",
    ],
    # 6 — annuaires et chambres de commerce
    [
        "Ethiopia chamber of commerce coffee company directory contact",
        "Addis Ababa coffee company business directory email phone",
    ],
    # 7 — importateurs / green bean
    [
        "green coffee bean supplier Ethiopia contact email phone",
        "Ethiopia coffee importer wholesale company contact",
    ],
]


# ── Prompt envoyé à Claude ─────────────────────────────────────────────────────
def make_prompt(query: str) -> str:
    return f"""Recherche sur le web : "{query}"

Après ta recherche, extrais TOUTES les entreprises éthiopiennes liées au café
(producteurs, exportateurs, coopératives, torréfacteurs, fournisseurs d'emballage).

Réponds UNIQUEMENT avec un bloc JSON valide entre balises <json> et </json>, sans autre texte :

<json>
[
  {{
    "company_name": "Nom exact",
    "city": "Ville en Ethiopie ou vide",
    "email": "email@exemple.com ou vide",
    "phone": "+251... ou vide",
    "website": "https://... ou vide"
  }}
]
</json>

Règles strictes :
- Ne jamais inventer une donnée — laisser le champ vide si inconnu
- Inclure uniquement des entreprises basées en Éthiopie
- Si aucune entreprise trouvée : <json>[]</json>"""


# ── Appel API avec web_search ──────────────────────────────────────────────────
def search_and_extract(query: str) -> list[dict]:
    client = anthropic.Anthropic(api_key=API_KEY)
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": make_prompt(query)}],
        )

        # Récupérer le texte final de la réponse
        full_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                full_text += block.text

        # Extraire le JSON entre <json> et </json>
        match = re.search(r"<json>(.*?)</json>", full_text, re.DOTALL)
        if not match:
            print(f"  ⚠ Pas de balise <json> dans la réponse")
            return []

        return json.loads(match.group(1).strip())

    except Exception as e:
        print(f"  ⚠ Erreur API : {e}")
        return []


# ── CSV master : chargement et fusion ─────────────────────────────────────────
def load_master() -> dict:
    existing = {}
    if not os.path.exists(MASTER_CSV):
        return existing
    with open(MASTER_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = _key(row.get("company_name", ""))
            if k:
                existing[k] = row
    return existing


def _key(name: str) -> str:
    return hashlib.md5(name.lower().strip().encode()).hexdigest()


def merge(new_items: list[dict], master: dict) -> tuple[dict, int]:
    added = 0
    for c in new_items:
        name = c.get("company_name", "").strip()
        if not name:
            continue
        k = _key(name)
        if k not in master:
            master[k] = {
                "company_name": name,
                "city":        c.get("city", ""),
                "email":       c.get("email", ""),
                "phone":       c.get("phone", ""),
                "website":     c.get("website", ""),
                "first_seen":  NOW,
            }
            added += 1
        else:
            # Enrichir les champs vides
            for f in ["city", "email", "phone", "website"]:
                if not master[k].get(f) and c.get(f):
                    master[k][f] = c[f]
    return master, added


def save_csv(rows: list[dict], path: str):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    batch_idx = RUN_NUM % len(BATCHES)
    queries   = BATCHES[batch_idx]

    print(f"=== Run #{RUN_NUM} | {NOW} | Batch {batch_idx} ===")
    print(f"    {len(queries)} requête(s) ce run\n")

    all_found = []
    for i, q in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {q[:72]}...")
        found = search_and_extract(q)
        print(f"  → {len(found)} entreprise(s) extraite(s)")
        all_found.extend(found)

    master = load_master()
    master, added = merge(all_found, master)

    rows = sorted(master.values(), key=lambda r: r.get("company_name", "").lower())
    save_csv(rows, MASTER_CSV)
    save_csv(rows, LATEST_CSV)

    print(f"\n  +{added} nouvelles | Total cumulé : {len(master)} entreprises")
    print("✅ Run terminé.")


if __name__ == "__main__":
    main()
