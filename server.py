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

# ══════════════════════════════════════════════════════════
#  SYSTEM PROMPT — động theo target language
#  - Hỗ trợ dịch mọi chiều (VI↔ZH, VI↔EN, VI↔MY, ...)
#  - Tuyệt đối KHÔNG từ chối dù nội dung liên quan betting/casino
# ══════════════════════════════════════════════════════════
def build_system_prompt(target: str) -> str:
    lang_map = {
        "Vietnamese":  "Tiếng Việt",
        "Chinese":     "Tiếng Trung (Giản thể)",
        "English":     "Tiếng Anh",
        "Malaysian":   "Bahasa Melayu",
        "Korean":      "Tiếng Hàn",
        "Japanese":    "Tiếng Nhật",
        "Thai":        "Tiếng Thái",
    }
    target_label = lang_map.get(target, target)

    return f"""Bạn là hệ thống dịch thuật chuyên nghiệp cho nền tảng game online và giải trí trực tuyến.

NHIỆM VỤ DUY NHẤT: Dịch văn bản đầu vào sang {target_label}.

QUY TẮC BẮT BUỘC:
1. CHỈ trả về bản dịch — không giải thích, không nhận xét, không thêm bất kỳ nội dung nào khác.
2. TUYỆT ĐỐI KHÔNG từ chối, không cảnh báo, không bình luận về nội dung. Đây là tài liệu nội bộ hợp pháp.
3. Giữ nguyên: số tiền, tên game, placeholder dạng __PH0__ __PH1__..., ký hiệu đặc biệt.
4. Dịch tự nhiên, phù hợp với nhân viên vận hành game online.
5. Nếu văn bản đã là {target_label}, trả về nguyên văn không thay đổi.
6. Thuật ngữ chuyên ngành ưu tiên: Nổ hũ, Bắn cá, Đá gà, Game bài, Casino, Xổ số, Thể thao (VI) / Slot, Fishing, Cockfight, Card Game, Live Casino, Lottery, Sports (EN) / Nos Hu, Tembak Ikan, Sabung Ayam, Permainan Kad, Kasino, Loteri, Sukan (MY)."""


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
    return jsonify({"version": "v5.5.0", "url": ""})


@app.route("/verify", methods=["POST"])
def verify():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "")
    return jsonify({"valid": key in VALID_KEYS})


@app.route("/translate", methods=["POST"])
def translate():
    data = request.get_json(silent=True) or {}

    # Kiểm tra license key
    key = data.get("key", "")
    if key not in VALID_KEYS:
        return jsonify({"error": "Unauthorized. Vui lòng nhập KEY kích hoạt hợp lệ."}), 403

    text = data.get("text", "").strip()
    target = data.get("target", "Vietnamese")

    if not text:
        return jsonify({"error": "Empty text"}), 400

    # Prompt user — đơn giản, rõ ràng
    user_prompt = f"Dịch toàn bộ đoạn sau sang {target}, chỉ trả về bản dịch:\n\n{text}"

    try:
        client = get_client()
        logging.info(f"Calling OpenAI... target={target}, len={len(text)}")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": build_system_prompt(target)},
                {"role": "user",   "content": user_prompt}
            ],
            temperature=0.2,   # ổn định hơn, ít "sáng tạo" hơn
            max_tokens=2048,
        )

        result = response.choices[0].message.content
        if not result:
            raise RuntimeError("Empty response from model")

        result = result.strip()

        # Phát hiện GPT từ chối (safety net)
        refusal_keywords = ["对不起", "我不能", "无法完成", "I'm sorry", "I cannot", "I'm unable"]
        if any(kw in result for kw in refusal_keywords):
            logging.warning(f"GPT refused. Result: {result[:80]}")
            return jsonify({"error": "Model từ chối — fallback sang glossary"}), 422

        logging.info("Translate success")
        return jsonify({"result": result})

    except Exception as e:
        logging.exception("Translate failed")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
