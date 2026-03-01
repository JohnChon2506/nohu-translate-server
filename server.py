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

    prompt = f"Translate to {target}. Only return translated text:\n{text}"

    try:
        client = get_client()

        print("CALLING OPENAI...")  # để xem log

        r = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )

        result = r.output[0].content[0].text
        print("RESULT:", result)

        return jsonify({"result": result})

    except Exception as e:
        print("OPENAI ERROR:", e)
        return jsonify({"error": str(e)}), 500


