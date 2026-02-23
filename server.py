from flask import Flask, request, jsonify
from openai import OpenAI
import os

app = Flask(__name__)
VALID_KEYS = {
    "CHONCHON-NOHU169",
    "JOHN-NOHU033",
    "CAOGE-55555"
}

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

@app.route("/translate", methods=["POST"])
@app.route("/verify", methods=["POST"])
def verify():
    data = request.get_json()
    key = data.get("key")

    if key in VALID_KEYS:
        return jsonify({"valid": True})
    else:
        return jsonify({"valid": False}), 403
def translate():
    data = request.json
    text = data.get("text", "")
    target = data.get("target", "Vietnamese")

    prompt = f"""
    Detect the language automatically and translate to {target}.
    Only return translated text.

    Text:
    {text}
    """

    try:
        r = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )
        return jsonify({"result": r.output_text.strip()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


