from flask import Flask, request, jsonify
from openai import OpenAI
import os

app = Flask(__name__)

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

@app.route("/translate", methods=["POST"])
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


app.run(host="0.0.0.0", port=10000)
