from flask import Flask, request, jsonify
from openai import OpenAI
import os
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

VALID_KEYS = {
    "CHONCHON-NOHU169",
    "JOHN-NOHU033",
    "CAOGE-55555"
}

def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY environment variable")
    return OpenAI(api_key=api_key)

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Server is running"})

@app.route("/verify", methods=["POST"])
def verify():
    data = request.get_json()
    key = data.get("key")
    return jsonify({"valid": key in VALID_KEYS})

@app.route("/translate", methods=["POST"])
def translate():
    data = request.json
    text = data.get("text", "")
    target = data.get("target", "Vietnamese")

    prompt = f"""Detect the language automatically and translate to {target}.
Only return translated text.
Text:
{text}"""

    try:
        client = get_client()

        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        return jsonify({"result": r.choices[0].message.content.strip()})

    except Exception as e:
        logging.exception("Translate error")
        return jsonify({"error": str(e)}), 500
