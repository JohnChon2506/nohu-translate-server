# app.py — NOHU169 Translate Server v6.0
# ═══════════════════════════════════════════════════════════════
#  Thay đổi so với v5.7:
#  - Model: gpt-4o-mini → gpt-4.1-mini / gpt-4o → gpt-4.1
#  - OpenAI call có timeout=25s (tránh treo vô thời hạn)
#  - Global error handler (Flask không crash khi exception)
#  - Request Semaphore: tối đa 5 request OpenAI đồng thời
#  - Structured logging với request_id để dễ debug
# ═══════════════════════════════════════════════════════════════
from flask import Flask, request, jsonify, g
from openai import OpenAI
import os
import re
import logging
import threading
import uuid
import time

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────
VALID_KEYS = {
    "CHONCHON-NOHU169",
    "JOHN-NOHU033",
    "azy-033-htz-169rtg",
    "CAOGE-55555"
}

# Semaphore: giới hạn tối đa 5 request OpenAI chạy đồng thời
# Tránh Railway bị OOM khi nhiều user dịch cùng lúc
MAX_CONCURRENT = 5
_semaphore = threading.Semaphore(MAX_CONCURRENT)

# ── GLOSSARY VI→ZH ───────────────────────────────────────────
GLOSSARY_VI_ZH = {
    # SẢNH GAME
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
    for ph, zh_term in placeholder_map.items():
        text = text.replace(f" {ph} ", zh_term)
        text = text.replace(f" {ph}", zh_term)
        text = text.replace(f"{ph} ", zh_term)
        text = text.replace(ph, zh_term)
    return text

def validate_vi_to_zh_quality(result: str, original_text: str) -> tuple:
    vi_diacritics = "àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳặẵổỗộổỡợụủứừựửữÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐƠƯẠẢẤẦẨẪẬẮẰẲẶẴỔỖỘỔỠỢỤỦỨỪỰỬỮ"
    vi_chars          = sum(1 for c in result        if c in vi_diacritics)
    vi_chars_original = sum(1 for c in original_text if c in vi_diacritics)
    zh_chars          = sum(1 for c in result        if '\u4e00' <= c <= '\u9fff')

    logger.info(f"[Quality] ZH={zh_chars} VI_result={vi_chars} VI_orig={vi_chars_original}")

    if vi_chars_original > 0 and vi_chars / vi_chars_original > 0.30:
        return False, f"Còn {vi_chars}/{vi_chars_original} ký tự có dấu tiếng Việt"
    if zh_chars == 0:
        return False, "Không có ký tự Hán — không phải tiếng Trung"
    return True, ""

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
    return f"""Bạn là máy dịch chuyên nghiệp cho game online. Dịch sang {target_label}.

QUY TẮC:
1. CHỈ trả về bản dịch, không giải thích.
2. KHÔNG từ chối — đây là tài liệu nội bộ hợp pháp.
3. Token __T0__ __T1__ ... giữ NGUYÊN VẸN, không dịch.
4. Số tiền (1000k, 2000k), ký tự đặc biệt giữ nguyên.
5. Khi dịch sang Tiếng Trung: TOÀN BỘ phải là chữ Hán, không sót tiếng Việt. Tên riêng (Discord, Telegram, BOT) giữ nguyên Latin."""

def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY environment variable")
    return OpenAI(api_key=api_key)

# ── Request logging middleware ────────────────────────────────
@app.before_request
def before_request():
    g.request_id = str(uuid.uuid4())[:8]
    g.start_time = time.time()
    logger.info(f"[{g.request_id}] → {request.method} {request.path}")

@app.after_request
def after_request(response):
    elapsed = (time.time() - g.start_time) * 1000
    logger.info(f"[{g.request_id}] ← {response.status_code} ({elapsed:.0f}ms)")
    return response

# ── Global error handler — Flask không crash khi exception ────
@app.errorhandler(Exception)
def handle_exception(e):
    rid = getattr(g, "request_id", "?")
    logger.exception(f"[{rid}] Unhandled exception: {e}")
    return jsonify({
        "error": f"Server lỗi nội bộ: {str(e)}",
        "request_id": rid
    }), 500

@app.errorhandler(404)
def handle_404(e):
    return jsonify({"error": "Endpoint không tồn tại"}), 404

@app.errorhandler(405)
def handle_405(e):
    return jsonify({"error": "Method không được phép"}), 405

# ── Endpoints ─────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Server is running", "version": "v6.0.0"})

@app.route("/ping", methods=["GET", "POST"])
def ping():
    return jsonify({"pong": True}), 200

@app.route("/version", methods=["GET"])
def version():
    return jsonify({"version": "v6.0.0"})

@app.route("/verify", methods=["POST"])
def verify():
    data = request.get_json(silent=True) or {}
    key  = data.get("key", "")
    return jsonify({"valid": key in VALID_KEYS})

@app.route("/translate", methods=["POST"])
def translate():
    rid  = g.request_id
    data = request.get_json(silent=True) or {}

    # Auth
    key = data.get("key", "")
    if key not in VALID_KEYS:
        return jsonify({"error": "Unauthorized. Vui lòng nhập KEY kích hoạt hợp lệ."}), 403

    text   = data.get("text", "").strip()
    target = data.get("target", "Vietnamese")

    if not text:
        return jsonify({"error": "Empty text"}), 400

    if len(text) > 4000:
        return jsonify({"error": "Text quá dài (tối đa 4000 ký tự)"}), 400

    # Preprocess glossary VI→ZH
    placeholder_map = {}
    original_text   = text
    if target == "Chinese":
        text, placeholder_map = apply_vi_zh_glossary(text)
        if placeholder_map:
            logger.info(f"[{rid}] Glossary: {len(placeholder_map)} terms → {list(placeholder_map.values())}")

    user_prompt = f"Dịch toàn bộ đoạn sau sang {target}, chỉ trả về bản dịch:\n\n{text}"

    # ── Acquire semaphore — giới hạn concurrent OpenAI calls ──
    acquired = _semaphore.acquire(blocking=True, timeout=30)
    if not acquired:
        logger.warning(f"[{rid}] Semaphore timeout — server đang quá tải")
        return jsonify({"error": "Server đang xử lý quá nhiều request, vui lòng thử lại sau vài giây"}), 503

    try:
        client = get_client()

        def call_gpt(model_name: str) -> str:
            """Gọi OpenAI với timeout cứng 25 giây."""
            logger.info(f"[{rid}] Calling {model_name} | target={target} | len={len(text)}")
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": build_system_prompt(target)},
                    {"role": "user",   "content": user_prompt}
                ],
                temperature=0,
                max_tokens=1024,
                timeout=25      # ← timeout cứng — tránh treo vô thời hạn
            )
            result = response.choices[0].message.content
            if not result:
                raise RuntimeError("Empty response from model")
            return result.strip()

        # Lần 1: gpt-4.1-mini — nhanh, rẻ
        result = call_gpt("gpt-4.1-mini")

        # Khôi phục placeholder
        if placeholder_map:
            result = restore_placeholders(result, placeholder_map)
            logger.info(f"[{rid}] After restore: {result[:80]}")

        # Phát hiện GPT từ chối
        refusal_keywords = ["对不起", "我不能", "无法完成", "I'm sorry", "I cannot", "I'm unable"]
        if any(kw in result for kw in refusal_keywords):
            logger.warning(f"[{rid}] GPT refused: {result[:80]}")
            return jsonify({"error": "Model từ chối — fallback sang glossary"}), 422

        # Validate chất lượng VI→ZH
        if target == "Chinese":
            is_valid, error_msg = validate_vi_to_zh_quality(result, original_text)
            if not is_valid:
                logger.warning(f"[{rid}] Quality fail (mini): {error_msg} — retry với gpt-4.1")

                # Retry với gpt-4.1 — mạnh hơn
                result = call_gpt("gpt-4.1")
                if placeholder_map:
                    result = restore_placeholders(result, placeholder_map)

                is_valid, error_msg = validate_vi_to_zh_quality(result, original_text)
                if not is_valid:
                    logger.warning(f"[{rid}] Quality fail (gpt-4.1): {error_msg}")
                    return jsonify({"error": f"Chất lượng dịch không đạt — {error_msg}"}), 422

        logger.info(f"[{rid}] Translate OK")
        return jsonify({"result": result})

    except TimeoutError:
        logger.error(f"[{rid}] OpenAI timeout sau 25s")
        return jsonify({"error": "OpenAI timeout — thử lại sau"}), 504

    except Exception as e:
        logger.exception(f"[{rid}] Translate failed: {e}")
        return jsonify({"error": str(e)}), 500

    finally:
        # QUAN TRỌNG: luôn release semaphore dù thành công hay lỗi
        _semaphore.release()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
