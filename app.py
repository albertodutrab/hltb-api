from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import re
import time

app = Flask(__name__)
CORS(app)

# ── Similaridade de strings (Levenshtein) ──────────────────────────────────────

def levenshtein(s1, s2):
    s1, s2 = s1.lower(), s2.lower()
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[len(s2)]

def similarity_score(query, candidate):
    query     = re.sub(r'[^a-z0-9 ]', '', query.lower().strip())
    candidate = re.sub(r'[^a-z0-9 ]', '', candidate.lower().strip())
    dist = levenshtein(query, candidate)
    max_len = max(len(query), len(candidate), 1)
    return 1 - dist / max_len

def best_match(query, candidates):
    scored = [(c, similarity_score(query, c.get('game_name', ''))) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0] if scored else None

# ── HowLongToBeat ──────────────────────────────────────────────────────────────

HLTB_BASE       = "https://howlongtobeat.com"
HLTB_INIT_URL   = HLTB_BASE + "/api/search/init"
HLTB_SEARCH_URL = HLTB_BASE + "/api/search"

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": HLTB_BASE + "/",
    "Origin":  HLTB_BASE,
    "Accept":  "*/*",
}

def get_auth_token():
    ts = int(time.time() * 1000)
    resp = requests.get(f"{HLTB_INIT_URL}?t={ts}", headers=BASE_HEADERS, timeout=10)
    print(f"[INIT] status={resp.status_code} body={resp.text[:300]}")
    resp.raise_for_status()
    data = resp.json()
    token = data.get("token") or data.get("auth_token") or data.get("value")
    if not token:
        for v in data.values():
            if isinstance(v, str) and len(v) > 8:
                token = v
                break
    print(f"[INIT] token obtido: {token}")
    return token

def build_payload(game_name):
    return {
        "searchType":    "games",
        "searchTerms":   game_name.split(),
        "searchPage":    1,
        "size":          10,
        "searchOptions": {
            "games": {
                "userId": 0, "platform": "", "sortCategory": "popular",
                "rangeCategory": "main", "rangeTime": {"min": None, "max": None},
                "gameplay": {"perspective": "", "flow": "", "genre": "", "subGenre": ""},
                "rangeYear": {"min": "", "max": ""}, "modifier": "",
            },
            "users":  {"sortCategory": "postcount"},
            "lists":  {"sortCategory": "follows"},
            "filter": "", "sort": 0, "randomizer": 0,
        },
        "useCache": True,
    }

def search_hltb(game_name):
    try:
        token = get_auth_token()
        headers = {**BASE_HEADERS, "Content-Type": "application/json"}
        if token:
            headers["x-auth-token"] = token

        resp = requests.post(
            HLTB_SEARCH_URL,
            headers=headers,
            json=build_payload(game_name),
            timeout=15,
        )
        print(f"[SEARCH] status={resp.status_code} body={resp.text[:300]}")
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as e:
        print(f"[SEARCH] ERRO: {e}")
        return []

def seconds_to_hours(seconds):
    if not seconds:
        return None
    return round(seconds / 3600, 1)

def parse_game(game):
    return {
        "game_name":     game.get("game_name", ""),
        "main_story":    seconds_to_hours(game.get("comp_main")),
        "main_extras":   seconds_to_hours(game.get("comp_plus")),
        "completionist": seconds_to_hours(game.get("comp_100")),
        "hltb_id":       game.get("game_id"),
        "image_url":     f"{HLTB_BASE}{game.get('game_image', '')}",
    }

# ── Rotas ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return jsonify({"status": "ok", "message": "HLTB API server running"})

@app.route("/debug")
def debug():
    """Rota de diagnóstico — mostra exatamente o que o HLTB retorna."""
    game_name = request.args.get("game", "the witcher 3").strip()
    result = {"init": {}, "search": {}}

    # Testa o /init
    try:
        ts = int(time.time() * 1000)
        r = requests.get(f"{HLTB_INIT_URL}?t={ts}", headers=BASE_HEADERS, timeout=10)
        result["init"]["status"] = r.status_code
        result["init"]["body"]   = r.text[:500]
    except Exception as e:
        result["init"]["error"] = str(e)

    # Testa o /search com token
    try:
        token = None
        if result["init"].get("status") == 200:
            data  = r.json()
            token = data.get("token") or data.get("auth_token") or data.get("value")
            if not token:
                for v in data.values():
                    if isinstance(v, str) and len(v) > 8:
                        token = v
                        break

        headers = {**BASE_HEADERS, "Content-Type": "application/json"}
        if token:
            headers["x-auth-token"] = token
        result["search"]["token_used"] = token

        r2 = requests.post(HLTB_SEARCH_URL, headers=headers,
                           json=build_payload(game_name), timeout=15)
        result["search"]["status"] = r2.status_code
        result["search"]["body"]   = r2.text[:800]
    except Exception as e:
        result["search"]["error"] = str(e)

    return jsonify(result)

@app.route("/hltb")
def hltb():
    game_name = request.args.get("game", "").strip()
    if not game_name:
        return jsonify({"error": "Parâmetro 'game' é obrigatório"}), 400

    results = search_hltb(game_name)
    if not results:
        return jsonify({"error": "Nenhum resultado encontrado", "query": game_name}), 404

    best = best_match(game_name, results)
    if not best:
        return jsonify({"error": "Não foi possível determinar o melhor resultado"}), 404

    return jsonify(parse_game(best))

@app.route("/hltb/all")
def hltb_all():
    game_name = request.args.get("game", "").strip()
    if not game_name:
        return jsonify({"error": "Parâmetro 'game' é obrigatório"}), 400

    results = search_hltb(game_name)
    parsed  = [parse_game(g) for g in results[:5]]
    for p, r in zip(parsed, results[:5]):
        p["similarity"] = round(similarity_score(game_name, r.get("game_name", "")), 3)
    parsed.sort(key=lambda x: x["similarity"], reverse=True)
    return jsonify(parsed)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
