"""
Agent prospection café Éthiopie
Recherche : DuckDuckGo (gratuit, sans clé)
Extraction : Claude Anthropic API
Résultat   : data/companies_master.csv + data/companies_latest.csv
"""

import os, csv, json, hashlib, re, time
from datetime import datetime
import urllib.request, urllib.parse
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY  = os.environ["ANTHROPIC_API_KEY"]
RUN_NUM  = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
NOW      = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
DATA_DIR = "data"
MASTER   = f"{DATA_DIR}/companies_master.csv"
LATEST   = f"{DATA_DIR}/companies_latest.csv"
FIELDS   = ["company_name", "city", "email", "phone", "website", "first_seen"]

# ── 8 batches de requêtes en rotation ─────────────────────────────────────────
BATCHES = [
    ["Ethiopian coffee export company contact email phone",
     "Ethiopia coffee trading company Addis Ababa contact"],
    ["Sidama coffee company Ethiopia email phone",
     "Yirgacheffe coffee producer exporter Ethiopia contact"],
    ["Jimma coffee Ethiopia company phone email",
     "Kaffa coffee Ethiopia exporter contact details"],
    ["Ethiopian coffee farmers cooperative union contact email",
     "Oromia coffee cooperative Ethiopia phone"],
    ["coffee roaster Ethiopia company email contact",
     "specialty coffee Ethiopia roasting company phone"],
    ["coffee packaging supplier Ethiopia email contact",
     "Ethiopia coffee bag manufacturer phone"],
    ["Ethiopia chamber commerce coffee company directory",
     "Addis Ababa coffee business directory email phone"],
    ["green coffee bean supplier Ethiopia email phone",
     "Ethiopia coffee importer wholesale contact"],
]

# ── DuckDuckGo HTML scrape (sans clé) ─────────────────────────────────────────
def search(query: str) -> str:
    try:
        q = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={q}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        titles   = re.findall(r'class="result__title".*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
        urls     = re.findall(r'class="result__url"[^>]*>(.*?)</span>', html, re.DOTALL)

        parts = []
        for i in range(min(len(snippets), 8)):
            t = re.sub(r"<[^>]+>", "", titles[i]).strip()   if i < len(titles)   else ""
            s = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            u = urls[i].strip()                              if i < len(urls)     else ""
            if t: parts.append(f"Titre: {t}")
            if s: parts.append(f"Extrait: {s}")
            if u: parts.append(f"URL: {u}")
            parts.append("---")

        result = "\n".join(parts)
        print(f"  → {len(snippets)} résultats récupérés")
        return result
    except Exception as e:
        print(f"  ⚠ Recherche : {e}")
        return ""

# ── Extraction Claude ──────────────────────────────────────────────────────────
PROMPT = """Voici des résultats de recherche sur : "{query}"

{results}

Extrais TOUTES les entreprises éthiopiennes liées au café (producteurs, exportateurs,
coopératives, torréfacteurs, emballage café).

Réponds UNIQUEMENT avec du JSON valide entre <json> et </json> :

<json>
[
  {{
    "company_name": "Nom exact",
    "city": "Ville en Ethiopie ou vide",
    "email": "email ou vide",
    "phone": "+251... ou vide",
    "website": "https://... ou vide"
  }}
]
</json>

Ne jamais inventer — laisser vide si inconnu. Si rien trouvé : <json>[]</json>"""


def extract(query: str, results_text: str) -> list[dict]:
    if not results_text.strip():
        return []
    client = anthropic.Anthropic(api_key=API_KEY)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": PROMPT.format(
                query=query, results=results_text[:4000]
            )}],
        )
        text = resp.content[0].text
        match = re.search(r"<json>(.*?)</json>", text, re.DOTALL)
        if not match:
            return []
        return json.loads(match.group(1).strip())
    except Exception as e:
        print(f"  ⚠ Claude : {e}")
        return []

# ── CSV master ────────────────────────────────────────────────────────────────
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

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    idx     = RUN_NUM % len(BATCHES)
    queries = BATCHES[idx]
    print(f"=== Run #{RUN_NUM} | {NOW} | Batch {idx} | {len(queries)} requêtes ===\n")

    all_found = []
    for i, q in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {q[:70]}...")
        results = search(q)
        if not results.strip():
            print("  → Aucun résultat")
            time.sleep(2)
            continue
        found = extract(q, results)
        print(f"  → {len(found)} entreprise(s) extraite(s)")
        all_found.extend(found)
        time.sleep(2)

    master = load_master()
    master, added = merge(all_found, master)
    rows = sorted(master.values(), key=lambda r: r.get("company_name", "").lower())
    save(rows, MASTER)
    save(rows, LATEST)

    print(f"\n  +{added} nouvelles | Total : {len(master)} entreprises")
    print("✅ Run terminé.")

if __name__ == "__main__":
    main()
