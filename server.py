from flask import Flask, request, jsonify
from openai import OpenAI
import os
import logging

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

VALID_KEYS = {
    "CHONCHON-NOHU169",
    "JOHN-NOHU033",
    "azy-033-htz-169rtg",
    "CAOGE-55555"
}

# Glossary thuật ngữ ZH→VI — giữ nguyên SYSTEM_PROMPT của bạn
SYSTEM_PROMPT = ""  # <-- giữ nguyên phần này của bạn

def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY environment variable")
    return OpenAI(api_key=api_key)

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Server is running"})

@app.route("/version", methods=["GET"])
def version():
    return jsonify({"version": "v5.4.0", "url": ""})

@app.route("/verify", methods=["POST"])
def verify():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "")
    return jsonify({"valid": key in VALID_KEYS})

@app.route("/translate", methods=["POST"])
def translate():
    data = request.get_json(silent=True) or {}

    # ✅ KIỂM TRA LICENSE KEY TRƯỚC KHI DỊCH
    key = data.get("key", "")
    if key not in VALID_KEYS:
        return jsonify({"error": "Unauthorized. Vui lòng nhập KEY kích hoạt hợp lệ."}), 403

    text = data.get("text", "").strip()
    target = data.get("target", "Vietnamese")
    if not text:
        return jsonify({"error": "Empty text"}), 400

    prompt = f"Dịch sang {target}:\n{text}"
    try:
        client = get_client()
        logging.info("Calling OpenAI...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )
        result = response.choices[0].message.content
        if not result:
            raise RuntimeError("Empty response from model")
        logging.info("Translate success")
        return jsonify({"result": result.strip()})
    except Exception as e:
        logging.exception("Translate failed")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
