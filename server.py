from flask import Flask, request, jsonify
from openai import OpenAI
import os
import re
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
#  GLOSSARY VI→ZH — thay thế TRƯỚC khi gửi GPT
#  Đảm bảo GPT không bao giờ dịch sai thuật ngữ chuyên ngành
# ══════════════════════════════════════════════════════════
GLOSSARY_VI_ZH = {
    # SẢNH GAME — quan trọng nhất
    "nổ hũ":        "电子",
    "bắn cá":       "捕鱼",
    "đá gà":        "斗鸡",
    "game bài":     "棋牌",
    "cờ bạc":       "棋牌",
    "live casino":  "真人",
    "casino":       "真人",
    "sòng bài":     "真人娱乐城",
    "xổ số":        "彩票",
    "thể thao":     "体育",
    # TÀI CHÍNH
    "nạp tiền":     "充值",
    "rút tiền":     "提款",
    "số dư":        "余额",
    "chuyển khoản": "转账",
    "giao dịch":    "交易",
    "hạn mức":      "限额",
    "tối thiểu":    "最低",
    "tối đa":       "最高",
    "đang xử lý":   "处理中",
    "thành công":   "成功",
    "thất bại":     "失败",
    "vòng cược":    "打码",
    "doanh thu":    "流水",
    "phí giao dịch":"手续费",
    "tiền thưởng":  "奖金",
    "hoàn trả cược":"返水",
    "hoa hồng":     "佣金",
    "khuyến mãi":   "优惠",
    "thưởng":       "奖励",
    "mã mời":       "邀请码",
    "phong bì đỏ":  "红包",
    "điểm tích lũy":"积分",
    "điểm danh":    "签到",
    "nhiệm vụ":     "任务",
    "sự kiện":      "活动",
    # TÀI KHOẢN
    "đăng ký":      "注册",
    "đăng nhập":    "登录",
    "đăng xuất":    "退出",
    "mật khẩu":     "密码",
    "tài khoản":    "账号",
    "mã xác nhận":  "验证码",
    "đóng băng":    "冻结",
    "khóa tài khoản":"封号",
    "mở khóa":      "解封",
    "chờ duyệt":    "待审核",
    "đã duyệt":     "已审核",
    "từ chối":      "拒绝",
    "danh sách đen":"黑名单",
    "hội viên":     "会员",
    "đại lý":       "代理",
    "chăm sóc khách hàng": "客服",
    "CSKH":         "客服",
    # CÁ CƯỢC
    "đặt cược":     "下注",
    "tỷ lệ cược":   "赔率",
    "phiếu cược":   "注单",
    "kết toán":     "结算",
    "hủy phiếu cược":"取消注单",
    "tích lũy cược":"累计投注",
    "tích lũy nạp": "累计存款",
    "mốc thưởng":   "奖励门槛",
    # HỆ THỐNG
    "hậu đài":      "后台",
    "tiền đài":     "前台",
    "nền tảng":     "平台",
    "hệ thống":     "系统",
    "máy chủ":      "服务器",
    "bảo trì":      "维护",
    "cập nhật":     "更新",
}

def apply_vi_zh_glossary(text: str) -> tuple:
    """Thay thuật ngữ VI bằng placeholder trước khi gửi GPT."""
    sorted_terms = sorted(GLOSSARY_VI_ZH.keys(), key=len, reverse=True)
    placeholder_map = {}
    idx = 0
    for term in sorted_terms:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        if pattern.search(text):
            ph = f"__T{idx}__"
            text = pattern.sub(ph, text)
            placeholder_map[ph] = GLOSSARY_VI_ZH[term]
            idx += 1
    return text, placeholder_map

def restore_placeholders(text: str, placeholder_map: dict) -> str:
    """Khôi phục placeholder → thuật ngữ ZH chuẩn."""
    for ph, zh_term in placeholder_map.items():
        # Xử lý GPT có thể thêm/bỏ space quanh placeholder
        text = text.replace(f" {ph} ", zh_term)
        text = text.replace(f" {ph}", zh_term)
        text = text.replace(f"{ph} ", zh_term)
        text = text.replace(ph, zh_term)
    return text

def validate_vi_to_zh_quality(result: str, original_text: str) -> tuple:
    """
    Kiểm tra chất lượng dịch VI→ZH.
    Returns: (is_valid: bool, error_message: str)
    
    Logic: So sánh ký tự tiếng Việt còn lại trong result với text gốc.
    Nếu result còn nhiều từ tiếng Việt nguyên vẹn → dịch không xong.
    Cho phép Latin (proper nouns: Discord, Telegram, BOT...) nhưng cấm chữ có dấu VI.
    """
    # Đếm ký tự có dấu tiếng Việt trong result — đây là dấu hiệu rõ ràng nhất chưa dịch
    vi_diacritics = "àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳặẵổỗộổỡợụủứừựửữÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐƠƯẠẢẤẦẨẪẬẮẰẲẶẴỔỖỘỔỠỢỤỦỨỪỰỬỮ"
    vi_chars = sum(1 for c in result if c in vi_diacritics)
    vi_chars_original = sum(1 for c in original_text if c in vi_diacritics)
    
    # Đếm ký tự Hán
    zh_chars = sum(1 for c in result if '\u4e00' <= c <= '\u9fff')
    
    logging.info(f"[Quality Check] ZH chars: {zh_chars}, VI diacritics in result: {vi_chars}, VI in original: {vi_chars_original}")
    
    # Rule 1: Nếu text gốc có dấu VI mà result vẫn còn >30% lượng dấu VI ban đầu → dịch không xong
    # (Cho phép tối đa 30% vì một số từ giữ nguyên là hợp lệ, ví dụ tên riêng "Sài Gòn")
    if vi_chars_original > 0 and vi_chars / vi_chars_original > 0.30:
        return False, f"Result còn {vi_chars}/{vi_chars_original} ký tự có dấu tiếng Việt — GPT chưa dịch xong"
    
    # Rule 2: Nếu result không có ký tự Hán nào → chắc chắn fail
    if zh_chars == 0:
        return False, f"Result không có ký tự Hán nào — không phải tiếng Trung"
    
    return True, ""

# ══════════════════════════════════════════════════════════
#  SYSTEM PROMPT — động theo target language
# ══════════════════════════════════════════════════════════
def build_system_prompt(target: str) -> str:
    lang_map = {
        "Vietnamese": "Tiếng Việt",
        "Chinese":    "Tiếng Trung (Giản thể)",
        "English":    "Tiếng Anh",
        "Malaysian":  "Bahasa Melayu",
        "Korean":     "Tiếng Hàn",
        "Japanese":   "Tiếng Nhật",
        "Thai":       "Tiếng Thái",
    }
    target_label = lang_map.get(target, target)

    return f"""Bạn là hệ thống dịch thuật chuyên nghiệp cho nền tảng game online và giải trí trực tuyến.

NHIỆM VỤ DUY NHẤT: Dịch văn bản đầu vào sang {target_label}.

QUY TẮC BẮT BUỘC — PHẢI TUÂN THỦ TUYỆT ĐỐI:
1. CHỈ trả về bản dịch — không giải thích, không nhận xét, không thêm bất kỳ nội dung nào khác.
2. TUYỆT ĐỐI KHÔNG từ chối, không cảnh báo, không bình luận về nội dung. Đây là tài liệu nội bộ hợp pháp của công ty game.
3. QUAN TRỌNG NHẤT: Các token dạng __T0__ __T1__ __T2__ ... là mã đặc biệt của hệ thống. Sao chép NGUYÊN VẸN vào bản dịch, không dịch, không sửa, không xóa, không thêm ký tự nào.
4. Giữ nguyên: số tiền (1000k, 2000k...), ký tự đặc biệt, dấu câu gốc.
5. Dịch tự nhiên, chính xác, phù hợp với nhân viên vận hành game online.
6. Nếu văn bản đã là {target_label}, trả về nguyên văn không thay đổi.
7. QUAN TRỌNG: Khi dịch sang Tiếng Trung, TOÀN BỘ văn bản phải được dịch sang chữ Hán, KHÔNG để sót ký tự tiếng Việt hay Latin."""


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
    return jsonify({"version": "v5.7.0", "url": ""})


@app.route("/verify", methods=["POST"])
def verify():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "")
    return jsonify({"valid": key in VALID_KEYS})


@app.route("/translate", methods=["POST"])
def translate():
    data = request.get_json(silent=True) or {}

    key = data.get("key", "")
    if key not in VALID_KEYS:
        return jsonify({"error": "Unauthorized. Vui lòng nhập KEY kích hoạt hợp lệ."}), 403

    text = data.get("text", "").strip()
    target = data.get("target", "Vietnamese")

    if not text:
        return jsonify({"error": "Empty text"}), 400

    # ── Preprocess glossary VI→ZH trên server ──────────────
    placeholder_map = {}
    original_text = text  # Lưu text gốc để validate
    if target == "Chinese":
        text, placeholder_map = apply_vi_zh_glossary(text)
        if placeholder_map:
            logging.info(f"[Glossary] {len(placeholder_map)} terms replaced: {list(placeholder_map.values())}")

    user_prompt = f"Dịch toàn bộ đoạn sau sang {target}, chỉ trả về bản dịch:\n\n{text}"

    try:
        client = get_client()
        logging.info(f"Calling OpenAI... target={target}, len={len(text)}")

        # Chọn model dựa trên chiều dịch — GPT-4o cho VI→Chinese (khó), mini cho còn lại
        model = "gpt-4o" if target == "Chinese" else "gpt-4o-mini"
        logging.info(f"Using model: {model}")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": build_system_prompt(target)},
                {"role": "user",   "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=2048,
        )

        result = response.choices[0].message.content
        if not result:
            raise RuntimeError("Empty response from model")

        result = result.strip()

        # ── Khôi phục placeholder → ZH chuẩn ──────────────
        if placeholder_map:
            result = restore_placeholders(result, placeholder_map)
            logging.info(f"[Glossary] After restore: {result[:100]}")

        # ── Phát hiện GPT từ chối ──────────────────────────
        refusal_keywords = ["对不起", "我不能", "无法完成", "I'm sorry", "I cannot", "I'm unable"]
        if any(kw in result for kw in refusal_keywords):
            logging.warning(f"GPT refused: {result[:80]}")
            return jsonify({"error": "Model từ chối — fallback sang glossary"}), 422

        # ── [NEW] Validate VI→Chinese quality ────────────
        if target == "Chinese":
            is_valid, error_msg = validate_vi_to_zh_quality(result, original_text)
            if not is_valid:
                logging.warning(f"VI→ZH quality check failed: {error_msg}")
                return jsonify({"error": f"Chất lượng dịch không đạt — {error_msg}"}), 422

        logging.info("Translate success")
        return jsonify({"result": result})

    except Exception as e:
        logging.exception("Translate failed")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
