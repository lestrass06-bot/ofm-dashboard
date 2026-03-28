import requests, json, time, os
from datetime import datetime

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUTPUT_FILE = "/root/veille_resultats.json"

def get_config():
    try:
        url = "https://raw.githubusercontent.com/lestrass06-bot/ofm-dashboard/main/veille_config.json"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return {
        "comptes": ["sarah.h44","joellperry","dahyn1xoficial","karen.katc","marcimorallxo","julia_delenes22","annatomaax","amandakabdedo","clari_cremaschi","itselodiexoxo"],
        "prompt": "Analyse ce reel Instagram pour une agence OFM. Note de 1-10. Retenir uniquement si: mouvement simple reproductible avec IA, pas trop suggestif, style sportif/aguicheur/lifestyle. Répondre en JSON: {recommande: bool, score: int, raison: string, style: string, conseil_kling: string}"
    }

def scrape_reels(username):
    print(f"Scraping @{username}...")
    url = "https://api.apify.com/v2/acts/apify-instagram-scraper/runs"
    headers = {"Content-Type":"application/json","Authorization":f"Bearer {APIFY_TOKEN}"}
    payload = {"directUrls":[f"https://www.instagram.com/{username}/"],"resultsType":"posts","resultsLimit":20,"addParentData":False}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        run_id = r.json().get("data",{}).get("id")
        if not run_id: return []
        for _ in range(30):
            time.sleep(10)
            sr = requests.get(f"https://api.apify.com/v2/actor-runs/{run_id}", headers=headers)
            status = sr.json().get("data",{}).get("status")
            if status == "SUCCEEDED": break
            if status in ["FAILED","ABORTED"]: return []
        dr = requests.get(f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items", headers=headers)
        items = dr.json().get("data",{}).get("items",[]) if isinstance(dr.json().get("data"),dict) else dr.json()
        reels = []
        for item in items:
            dur = item.get("videoDuration",0) or 0
            if 4 <= dur <= 16:
                reels.append({
                    "username": username,
                    "url": item.get("url",""),
                    "views": item.get("videoPlayCount",0) or 0,
                    "duration": dur,
                    "caption": (item.get("caption","") or "")[:100],
                    "thumbnail": item.get("displayUrl","")
                })
        print(f"  {len(reels)} reels ok")
        return reels
    except Exception as e:
        print(f"  Erreur: {e}")
        return []

def analyse(reel):
    config = get_config()
    prompt_base = config.get("prompt","")
    headers = {"Content-Type":"application/json","x-api-key": ANTHROPIC_KEY, "anthropic-version":"2023-06-01"}
    prompt = f"{prompt_base}\n\nReel: @{reel['username']}, {reel['views']} vues, {reel['duration']}s\nCaption: {reel['caption']}\nThumbnail: {reel['thumbnail']}\n\nRéponds UNIQUEMENT en JSON valide."
    body = {"model":"claude-sonnet-4-20250514","max_tokens":300,"messages":[{"role":"user","content":prompt}]}
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=30)
        text = r.json()["content"][0]["text"].strip()
        if text.startswith("```"): text = text.split("```")[1].replace("json","").strip()
        return json.loads(text)
    except Exception as e:
        print(f"  Analyse erreur: {e}")
        return None

def upload_github(filepath):
    import base64
    if not GITHUB_TOKEN: return
    with open(filepath,"rb") as f: content = base64.b64encode(f.read()).decode()
    url = "https://api.github.com/repos/lestrass06-bot/ofm-dashboard/contents/veille_resultats.json"
    headers = {"Authorization":f"token {GITHUB_TOKEN}","Content-Type":"application/json"}
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha","") if r.status_code == 200 else ""
    data = {"message":"update veille auto","content":content}
    if sha: data["sha"] = sha
    requests.put(url, headers=headers, json=data)
    print("JSON uploadé sur GitHub ✅")

def main():
    print(f"VEILLE - {datetime.now()}")
    config = get_config()
    comptes = config.get("comptes", [])
    print(f"Comptes: {comptes}")
    tous = []
    for c in comptes:
        tous += scrape_reels(c)
        time.sleep(5)
    print(f"Total: {len(tous)}")
    resultats = []
    for r in tous:
        a = analyse(r)
        r["analyse"] = a
        if a and a.get("recommande"):
            resultats.append(r)
            print(f"  OK {a.get('score')}/10 - {a.get('raison')}")
        else:
            print(f"  Ignore: {a.get('raison') if a else 'erreur'}")
        time.sleep(2)
    resultats.sort(key=lambda x: x["analyse"].get("score",0), reverse=True)
    with open(OUTPUT_FILE,"w",encoding="utf-8") as f:
        json.dump({"date":datetime.now().isoformat(),"total":len(tous),"recommandes":len(resultats),"reels":resultats}, f, ensure_ascii=False, indent=2)
    print(f"FINI: {len(resultats)} recommandes sur {len(tous)}")
    upload_github(OUTPUT_FILE)

if __name__ == "__main__":
    main()