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
    data = request.get_json(silent=True) or {}
    key = data.get("key", "")
    return jsonify({"valid": key in VALID_KEYS})


@app.route("/translate", methods=["POST"])
def translate():
    data = request.get_json(silent=True) or {}

    text = data.get("text", "").strip()
    target = data.get("target", "Vietnamese")

    if not text:
        return jsonify({"error": "Empty text"}), 400

    prompt = f"Translate the following text to {target}. Only return the translated text:\n{text}"

    try:
        client = get_client()

        logging.info("Calling OpenAI...")

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )

        # Lấy text an toàn (không index cứng)
        result = response.output_text

        if not result:
            raise RuntimeError("Empty response from model")

        logging.info("Translate success")

        return jsonify({"result": result.strip()})

    except Exception as e:
        logging.exception("Translate failed")
        return jsonify({"error": str(e)}), 500
