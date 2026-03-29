import os, json, time, requests
from datetime import datetime, timedelta

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
        "prompt": "Analyse ce reel Instagram pour une agence OFM. Note de 1-10. Retenir uniquement si: mouvement simple reproductible avec IA, pas de bikini, style sportif/aguicheur/lifestyle, duree 4-16s, ne parle pas ou parle francais. Reponds UNIQUEMENT en JSON: {recommande: bool, score: int, raison: string, style: string, conseil_kling: string}"
    }

def scrape_reels(username):
    print(f"Scraping @{username}...")
    url = "https://api.apify.com/v2/acts/apify~instagram-scraper/runs"
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
        items = dr.json() if isinstance(dr.json(), list) else []
        reels = []
        cutoff = datetime.now() - timedelta(days=7)
        for item in items:
            dur = item.get("videoDuration",0) or 0
            timestamp = item.get("timestamp","")
            try:
                post_date = datetime.fromisoformat(timestamp.replace("Z","+00:00")).replace(tzinfo=None)
                if post_date < cutoff:
                    continue
            except:
                pass
            if 4 <= dur <= 16:
                reels.append({
                    "username": username,
                    "url": item.get("url",""),
                    "views": item.get("videoPlayCount",0) or 0,
                    "duration": dur,
                    "caption": (item.get("caption","") or "")[:100],
                    "thumbnail": item.get("displayUrl",""),
                    "timestamp": timestamp
                })
        return reels
    except Exception as e:
        print(f"Erreur {username}: {e}")
        return []

def analyse(reel, prompt):
    try:
        headers = {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        msg = f"{prompt}\n\nReel: @{reel['username']} | {reel['views']} vues | {reel['duration']}s | Caption: {reel['caption']}"
        data = {"model":"claude-haiku-4-5-20251001","max_tokens":300,"messages":[{"role":"user","content":msg}]}
        r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=data, timeout=30)
        text = r.json()["content"][0]["text"]
        text = text.strip().replace("```json","").replace("```","")
        return json.loads(text)
    except:
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
    print("JSON uploade sur GitHub")

def main():
    print(f"VEILLE - {datetime.now()}")
    config = get_config()
    comptes = config.get("comptes", [])
    prompt = config.get("prompt", "")
    print(f"Comptes: {comptes}")
    tous = []
    for c in comptes:
        tous += scrape_reels(c)
        time.sleep(5)
    print(f"Total reels (7j): {len(tous)}")
    resultats = []
    for r in tous:
        a = analyse(r, prompt)
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
