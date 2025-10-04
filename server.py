from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

players = []  # [{sid, name}]
game_data = {
    "phrase": "",
    "masked": "",
    "wrong_guesses": [],
    "tries_left": 9,
    "scores": [0, 0],
    "round": 1
}

def mask_phrase(phrase):
    return "".join("_" if c.isalpha() else c for c in phrase)

def get_player_index(sid):
    for i, p in enumerate(players):
        if p["sid"] == sid:
            return i
    return -1

@socketio.on("connect")
def handle_connect(auth=None):
    sid = request.sid
    print(f"Player connected: {sid}")
    if len(players) < 2:
        players.append({"sid": sid, "name": None})
        emit("player_number", len(players))
    else:
        emit("message", "Game room full. Only two players allowed.")

@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    for p in players:
        if p["sid"] == sid:
            players.remove(p)
    emit("message", "A player disconnected. Game stopped.", broadcast=True)

@socketio.on("set_nickname")
def handle_nickname(data):
    sid = request.sid
    idx = get_player_index(sid)
    if idx != -1:
        players[idx]["name"] = data["nickname"]
        emit("message", f"{data['nickname']} joined the game!", broadcast=True)

    if len(players) == 2 and all(p["name"] for p in players):
        emit("message", f"Both players ready! {players[0]['name']} starts as the giver.", broadcast=True)
        emit("show_phrase_input", room=players[0]["sid"])

@socketio.on("set_phrase")
def handle_set_phrase(data):
    phrase = data["phrase"].lower()
    game_data["phrase"] = phrase
    game_data["masked"] = mask_phrase(phrase)
    game_data["wrong_guesses"] = []
    game_data["tries_left"] = 9

    giver = players[(game_data["round"] + 1) % 2]
    guesser = players[game_data["round"] % 2]

    # Giver sees the phrase clearly
    emit("show_giver_phrase", phrase, room=giver["sid"])

    # Guesser sees masked phrase
    emit("display_phrase", game_data["masked"], room=guesser["sid"])
    emit("update_tries", game_data["tries_left"], broadcast=True)

    emit("message", f"{giver['name']} has set the phrase! {guesser['name']}, start guessing.", broadcast=True)
    emit("show_guess_input", room=guesser["sid"])

@socketio.on("guess_letter")
def handle_guess(data):
    letter = data["letter"].lower()
    phrase = game_data["phrase"]
    masked = list(game_data["masked"])

    giver = players[(game_data["round"] + 1) % 2]
    guesser = players[game_data["round"] % 2]

    if letter in phrase:
        for i, ch in enumerate(phrase):
            if ch == letter:
                masked[i] = letter
        game_data["masked"] = "".join(masked)
        emit("display_phrase", game_data["masked"], broadcast=True)
        emit("update_tries", game_data["tries_left"], broadcast=True)

        if "_" not in game_data["masked"]:
            game_data["scores"][game_data["round"] % 2] += 1
            emit("message", f"🎉 {guesser['name']} guessed it right!", broadcast=True)
            emit("scores", {"p1": game_data["scores"][0], "p2": game_data["scores"][1]}, broadcast=True)
            switch_roles()
    else:
        if letter not in game_data["wrong_guesses"]:
            game_data["wrong_guesses"].append(letter)
            game_data["tries_left"] -= 1
        emit("wrong_guess", game_data["wrong_guesses"], broadcast=True)
        emit("update_tries", game_data["tries_left"], broadcast=True)

        if game_data["tries_left"] <= 0:
            # Reveal phrase when guesser fails
            emit("reveal_phrase", phrase, broadcast=True)
            game_data["scores"][(game_data["round"] + 1) % 2] += 1
            emit("message", f"😢 {giver['name']} wins this round! The phrase was '{phrase}'.", broadcast=True)
            emit("scores", {"p1": game_data["scores"][0], "p2": game_data["scores"][1]}, broadcast=True)
            switch_roles()

def switch_roles():
    """Swap roles after each round."""
    game_data["round"] += 1
    game_data["phrase"] = ""
    game_data["masked"] = ""
    game_data["wrong_guesses"] = []
    game_data["tries_left"] = 9

    giver = players[(game_data["round"] + 1) % 2]
    guesser = players[game_data["round"] % 2]

    emit("message", f"Next round! {giver['name']} is now the giver.", broadcast=True)
    emit("show_phrase_input", room=giver["sid"])
    emit("hide_guess_input", room=guesser["sid"])
    emit("clear_giver_phrase", room=giver["sid"])
    emit("clear_giver_phrase", room=guesser["sid"])

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)