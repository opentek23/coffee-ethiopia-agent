"""
Agent prospection café Éthiopie
Méthode : Claude fait lui-même la recherche web (outil natif Anthropic)
Zéro dépendance externe — uniquement la clé ANTHROPIC_API_KEY
"""

import os, csv, json, hashlib, re, time
from datetime import datetime
import anthropic

API_KEY  = os.environ["ANTHROPIC_API_KEY"]
RUN_NUM  = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
NOW      = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
DATA_DIR = "data"
MASTER   = f"{DATA_DIR}/companies_master.csv"
LATEST   = f"{DATA_DIR}/companies_latest.csv"
FIELDS   = ["company_name", "city", "email", "phone", "website", "first_seen"]

BATCHES = [
    [
        "Find Ethiopian coffee export companies with their email address and phone number in Addis Ababa",
        "List coffee trading companies based in Ethiopia with contact details email phone",
    ],
    [
        "Find Sidama and Yirgacheffe coffee producer companies in Ethiopia with email and phone",
        "Ethiopian coffee cooperative union contact email phone number list",
    ],
    [
        "Coffee roaster companies in Ethiopia Addis Ababa with email contact",
        "Jimma Kaffa coffee exporter Ethiopia company email phone",
    ],
    [
        "Ethiopian specialty coffee company export contact email phone website",
        "Oromia coffee farmers cooperative Ethiopia contact details",
    ],
    [
        "Coffee packaging supplier company Ethiopia email phone contact",
        "Ethiopia green coffee bean exporter company contact email",
    ],
    [
        "Ethiopian coffee company directory listing email phone Addis Ababa",
        "Coffee producer Ethiopia wholesale supplier contact information",
    ],
    [
        "Ethiopia coffee association member companies email phone",
        "Addis Ababa coffee importer exporter company contact email phone",
    ],
    [
        "Ethiopian coffee brand company website email contact phone",
        "Coffee processing company Ethiopia contact details email",
    ],
]

PROMPT = """Search the web and find Ethiopian companies working in the coffee industry 
(exporters, producers, cooperatives, roasters, packaging suppliers).

For this search: {query}

After searching, extract ALL companies you find and respond ONLY with valid JSON between <json> and </json> tags:

<json>
[
  {{
    "company_name": "Exact company name",
    "city": "City in Ethiopia or empty",
    "email": "email@example.com or empty",
    "phone": "+251... or empty",
    "website": "https://... or empty"
  }}
]
</json>

Rules:
- Only Ethiopian companies related to coffee
- Never invent data — leave field empty if unknown
- If nothing found: <json>[]</json>"""


def search_and_extract(query: str) -> list[dict]:
    client = anthropic.Anthropic(api_key=API_KEY)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3
            }],
            messages=[{"role": "user", "content": PROMPT.format(query=query)}],
        )

        # Récupérer tout le texte de la réponse finale
        full_text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                full_text += block.text

        print(f"  → Réponse reçue ({len(full_text)} chars)")

        match = re.search(r"<json>(.*?)</json>", full_text, re.DOTALL)
        if not match:
            print("  ⚠ Pas de JSON trouvé")
            return []

        data = json.loads(match.group(1).strip())
        return data

    except Exception as e:
        print(f"  ⚠ Erreur : {e}")
        return []


def _key(name: str) -> str:
    return hashlib.md5(name.lower().strip().encode()).hexdigest()

def load_master() -> dict:
    if not os.path.exists(MASTER):
        return {}
    with open(MASTER, newline="", encoding="utf-8") as f:
        return {_key(r["company_name"]): r for r in csv.DictReader(f) if r.get("company_name")}

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
                "city":    c.get("city", ""),
                "email":   c.get("email", ""),
                "phone":   c.get("phone", ""),
                "website": c.get("website", ""),
                "first_seen": NOW,
            }
            added += 1
        else:
            for f in ["city", "email", "phone", "website"]:
                if not master[k].get(f) and c.get(f):
                    master[k][f] = c[f]
    return master, added

def save(rows: list[dict], path: str):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

def main():
    idx     = RUN_NUM % len(BATCHES)
    queries = BATCHES[idx]
    print(f"=== Run #{RUN_NUM} | {NOW} | Batch {idx} | {len(queries)} requêtes ===\n")

    all_found = []
    for i, q in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {q[:70]}...")
        found = search_and_extract(q)
        print(f"  → {len(found)} entreprise(s) extraite(s)")
        all_found.extend(found)
        time.sleep(3)

    master = load_master()
    master, added = merge(all_found, master)
    rows = sorted(master.values(), key=lambda r: r.get("company_name", "").lower())
    save(rows, MASTER)
    save(rows, LATEST)

    print(f"\n  +{added} nouvelles | Total : {len(master)} entreprises")
    print("✅ Run terminé.")

if __name__ == "__main__":
    main()
