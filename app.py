from flask import Flask, request, jsonify
from howlongtobeatpy import HowLongToBeat
from difflib import SequenceMatcher

app = Flask(__name__)

def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "message": "HLTB API server running"
    })

@app.route("/hltb")
def hltb():
    game = request.args.get("game")

    if not game:
        return jsonify({"error": "Game parameter required"}), 400

    try:
        results = HowLongToBeat().search(game)

        if not results:
            return jsonify({
                "error": "Nenhum resultado encontrado",
                "query": game
            }), 404

        best_match = max(
            results,
            key=lambda x: similarity(game, x.game_name)
        )

        return jsonify({
            "game_name": best_match.game_name,
            "main_story": best_match.main_story,
            "main_extras": best_match.main_extra,
            "completionist": best_match.completionist
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

if __name__ == "__main__":
    app.run(debug=True)
