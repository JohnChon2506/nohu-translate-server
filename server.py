# app.py — NOHU169 Translate Server v6.1
# ═══════════════════════════════════════════════════════════════
#  Thay đổi so với v6.0:
#  - [FIX] Thêm variants số vào GLOSSARY_VI_ZH:
#      "đợi 1 chút", "chờ 1 chút", "đợi 1 lúc", v.v.
#      (v6.0 chỉ có "đợi một chút" — số "1" không khớp)
#  - [FIX] apply_vi_zh_glossary: nếu toàn bộ text đã là chữ Hán
#      sau khi apply → trả về nguyên không gửi GPT (tránh nguyên văn)
#  - [FIX] /version endpoint trả về "v6.1.0" để client tự cập nhật
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
    # ══ SẢNH GAME ══
    "nổ hũ":                "电子",
    "bắn cá":               "捕鱼",
    "đá gà":                "斗鸡",
    "game bài":             "棋牌",
    "cờ bạc":               "棋牌",
    "live casino":          "真人",
    "casino":               "真人",
    "sòng bài":             "真人娱乐城",
    "xổ số":                "彩票",
    "thể thao":             "体育",
    "thể thao điện tử":     "电子竞技",
    "esports":              "电子竞技",
    "slot":                 "电子老虎机",
    "baccarat":             "百家乐",
    "rồng hổ":              "龙虎",
    "tài xỉu":              "骰宝",
    "roulette":             "轮盘",
    "poker":                "扑克",
    "xì dách":              "二十一点",

    # ══ TÀI CHÍNH — NẠP RÚT ══
    "nạp tiền":             "充值",
    "nạp lần đầu":          "首充",
    "nạp lần đầu tiên":     "首次充值",
    "rút tiền":             "提款",
    "rút lần đầu":          "首次提款",
    "số dư":                "余额",
    "số dư khả dụng":       "可用余额",
    "chuyển khoản":         "转账",
    "giao dịch":            "交易",
    "lịch sử giao dịch":    "交易记录",
    "lịch sử nạp rút":      "存提记录",
    "hạn mức":              "限额",
    "hạn mức ngày":         "每日限额",
    "tối thiểu":            "最低",
    "tối đa":               "最高",
    "số tiền":              "金额",
    "tổng tiền":            "总金额",
    "phí giao dịch":        "手续费",
    "về tài khoản":         "到账",
    "chưa về":              "未到账",
    "đang xử lý":           "处理中",
    "đã xử lý":             "已处理",
    "thành công":           "成功",
    "thất bại":             "失败",
    "nạp thành công":       "充值成功",
    "nạp thất bại":         "充值失败",
    "rút thành công":       "提款成功",
    "rút thất bại":         "提款失败",
    "giao dịch thành công": "交易成功",
    "giao dịch thất bại":   "交易失败",
    "đang chờ xử lý":       "待处理",
    "hoàn tiền":            "退款",
    "hoàn trả":             "返还",

    # ══ NGÂN HÀNG & THANH TOÁN ══
    "thẻ ngân hàng":        "银行卡",
    "ngân hàng":            "银行",
    "tên chủ tài khoản":    "户名",
    "số tài khoản":         "卡号",
    "chi nhánh":            "支行",
    "ngân hàng mở tài khoản": "开户行",
    "người nhận":           "收款人",
    "biên lai":             "凭证",
    "biên lai chuyển khoản":"转账凭证",
    "ảnh chuyển khoản":     "转账截图",
    "internet banking":     "网银",
    "ví điện tử":           "电子钱包",
    "mã QR":                "二维码",
    "quét mã":              "扫码",
    "tiền điện tử":         "加密货币",
    "địa chỉ ví":           "钱包地址",

    # ══ VÒNG CƯỢC & DOANH THU ══
    "vòng cược":            "打码",
    "yêu cầu vòng cược":    "打码要求",
    "doanh thu":            "流水",
    "tổng doanh thu":       "总流水",
    "doanh thu hợp lệ":     "有效流水",
    "doanh thu không hợp lệ": "无效流水",
    "tích lũy cược":        "累计投注",
    "tích lũy nạp":         "累计存款",
    "mốc thưởng":           "奖励门槛",

    # ══ KHUYẾN MÃI & THƯỞNG ══
    "khuyến mãi":           "优惠",
    "thưởng":               "奖励",
    "tiền thưởng":          "奖金",
    "thưởng chào mừng":     "欢迎奖励",
    "thưởng nạp lần đầu":   "首充奖励",
    "thưởng sinh nhật":     "生日奖励",
    "thưởng tuần":          "周奖励",
    "thưởng tháng":         "月奖励",
    "thưởng nâng cấp":      "升级奖励",
    "hoàn trả cược":        "返水",
    "tỷ lệ hoàn trả":       "返水比例",
    "hoa hồng":             "佣金",
    "hoa hồng đại lý":      "代理佣金",
    "mã mời":               "邀请码",
    "phong bì đỏ":          "红包",
    "điểm tích lũy":        "积分",
    "đổi điểm":             "积分兑换",
    "điểm danh":            "签到",
    "nhiệm vụ":             "任务",
    "sự kiện":              "活动",
    "sự kiện giới hạn":     "限时活动",
    "nhận thưởng":          "领取奖励",
    "đủ điều kiện":         "符合条件",
    "chưa đủ điều kiện":    "不符合条件",
    "điều kiện":            "条件",
    "điều khoản":           "条款",
    "hết hạn":              "已过期",
    "có hiệu lực":          "有效",

    # ══ TÀI KHOẢN & BẢO MẬT ══
    "đăng ký":              "注册",
    "đăng ký thành công":   "注册成功",
    "đăng nhập":            "登录",
    "đăng xuất":            "退出",
    "tên đăng nhập":        "用户名",
    "mật khẩu":             "密码",
    "đổi mật khẩu":         "修改密码",
    "quên mật khẩu":        "忘记密码",
    "tài khoản":            "账号",
    "mã xác nhận":          "验证码",
    "xác minh danh tính":   "身份验证",
    "họ tên":               "姓名",
    "số điện thoại":        "手机号",
    "liên kết":             "绑定",
    "hủy liên kết":         "解绑",
    "đóng băng":            "冻结",
    "khóa tài khoản":       "封号",
    "tài khoản bị khóa":    "账号被封",
    "mở khóa":              "解封",
    "chờ duyệt":            "待审核",
    "đã duyệt":             "已审核",
    "từ chối":              "拒绝",
    "danh sách đen":        "黑名单",
    "hội viên":             "会员",
    "hội viên mới":         "新会员",
    "đại lý":               "代理",
    "đại lý cấp dưới":      "下级代理",
    "chăm sóc khách hàng":  "客服",
    "CSKH":                 "客服",

    # ══ CÁ CƯỢC ══
    "đặt cược":             "下注",
    "tỷ lệ cược":           "赔率",
    "phiếu cược":           "注单",
    "lịch sử đặt cược":     "投注记录",
    "tổng cược":            "总投注",
    "cược đơn":             "单式投注",
    "cược xiên":            "串关投注",
    "kết toán":             "结算",
    "đã kết toán":          "已结算",
    "chưa kết toán":        "未结算",
    "hủy phiếu cược":       "取消注单",
    "phiếu cược hợp lệ":    "有效注单",
    "phiếu cược không hợp lệ": "无效注单",
    "đang chờ kết quả":     "待开奖",
    "đã thắng":             "已赢",
    "đã thua":              "已输",
    "tiền thắng":           "赢利",
    "tiền thua":            "亏损",

    # ══ THỂ THAO ══
    "kèo chấp":             "让球盘",
    "kèo tài xỉu":          "大小盘",
    "kèo 1x2":              "独赢盘",
    "hiệp 1":               "上半场",
    "hiệp 2":               "下半场",
    "toàn trận":            "全场",
    "tỷ số":                "比分",
    "tỷ số cuối":           "最终比分",
    "trận đấu":             "赛事",
    "đội chủ nhà":          "主队",
    "đội khách":            "客队",
    "hòa":                  "平局",
    "trực tiếp":            "直播",
    "giải đấu":             "联赛",

    # ══ XỔ SỐ ══
    "kỳ":                   "期",
    "kỳ hiện tại":          "当前期",
    "kỳ tiếp theo":         "下一期",
    "kết quả xổ số":        "开奖结果",
    "số trúng thưởng":      "中奖号码",
    "trúng thưởng":         "中奖",
    "không trúng":          "未中奖",
    "giải đặc biệt":        "特别奖",
    "giải nhất":            "一等奖",
    "đóng cược":            "封盘",
    "mở cược":              "开盘",
    "xổ số miền Bắc":       "北部彩票",
    "xổ số miền Nam":       "南部彩票",
    "xổ số miền Trung":     "中部彩票",

    # ══ CHĂM SÓC KHÁCH HÀNG ══
    "xin chào":             "您好",
    "kính chào":            "尊敬的您好",
    "cảm ơn":               "谢谢",
    "xin lỗi":              "抱歉",
    "vui lòng":             "请",
    "vui lòng đợi":         "请稍等",
    "đợi một chút":         "稍等一下",
    "đợi 1 chút":           "稍等一下",   # [FIX v6.1] variant số "1"
    "đợi một lúc":          "稍等一下",
    "đợi 1 lúc":            "稍等一下",   # [FIX v6.1] variant số "1"
    "chờ một chút":         "稍等一下",
    "chờ 1 chút":           "稍等一下",   # [FIX v6.1] variant số "1"
    "chờ một lúc":          "稍等一下",
    "chờ 1 lúc":            "稍等一下",   # [FIX v6.1] variant số "1"
    "đợi chút":             "稍等",
    "chờ chút":             "稍等",
    "đợi tôi":              "等我一下",
    "để tôi kiểm tra":      "让我查一下",
    "tôi sẽ kiểm tra":      "我来查询",
    "để tôi xem":           "让我看看",
    "kiểm tra":             "查询",
    "tra cứu":              "查询",
    "liên hệ":              "联系",
    "hỗ trợ":               "支持",
    "phản hồi":             "回复",
    "khiếu nại":            "投诉",
    "báo cáo lỗi":          "报告问题",
    "sự cố":                "故障",
    "lỗi hệ thống":         "系统错误",
    "chụp màn hình":        "截图",
    "gửi ảnh":              "发图",

    # ══ KIỂM SOÁT RỦI RO ══
    "gian lận":             "欺诈",
    "giả mạo":              "伪造",
    "tài khoản ảo":         "虚假账号",
    "nhiều tài khoản":      "多账号",
    "cùng IP":              "相同IP",
    "chặn IP":              "封锁IP",
    "thiết bị giống nhau":  "相同设备",
    "đánh bạc bất hợp pháp":"非法赌博",
    "rửa tiền":             "洗钱",

    # ══ HỆ THỐNG ══
    "hậu đài":              "后台",
    "tiền đài":             "前台",
    "nền tảng":             "平台",
    "hệ thống":             "系统",
    "máy chủ":              "服务器",
    "bảo trì":              "维护",
    "đang bảo trì":         "维护中",
    "cập nhật":             "更新",
    "phiên bản mới":        "新版本",
    "tải lại":              "刷新",
    "đăng xuất và đăng nhập lại": "重新登录",
}


def _is_all_chinese(text: str) -> bool:
    """Kiểm tra xem text có phải toàn chữ Hán/số/dấu câu không (không còn tiếng Việt)."""
    stripped = re.sub(r'[\s\d,.\-!?@#$%^&*()_+=\[\]{};:\'\"<>/\\|`~]', '', text)
    if not stripped:
        return False
    zh_count = sum(1 for c in stripped if '\u4e00' <= c <= '\u9fff')
    return zh_count / len(stripped) >= 0.80


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
    return jsonify({"status": "ok", "message": "Server is running", "version": "v6.1.0"})

@app.route("/ping", methods=["GET", "POST"])
def ping():
    return jsonify({"pong": True}), 200

@app.route("/version", methods=["GET"])
def version():
    return jsonify({"version": "v6.1.0"})

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

        # [FIX v6.1] Nếu sau khi restore placeholder, text đã là toàn chữ Hán
        # → không cần gọi GPT, trả về luôn.
        # Trường hợp: client gửi "等一下" (đã bị custom glossary phía client convert),
        # hoặc toàn bộ text VI được glossary server resolve hết → tránh GPT trả nguyên văn ZH.
        if placeholder_map:
            preview = restore_placeholders(text, placeholder_map)
        else:
            preview = text

        if _is_all_chinese(preview):
            logger.info(f"[{rid}] Glossary fully resolved to ZH, skip GPT: {preview[:60]}")
            return jsonify({"result": preview})

        # Trường hợp: client gửi thẳng text ZH (không có placeholder nào match)
        if not placeholder_map and _is_all_chinese(text):
            logger.info(f"[{rid}] Input already ZH, return as-is: {text[:60]}")
            return jsonify({"result": text})

    user_prompt = f"Dịch toàn bộ đoạn sau sang {target}, chỉ trả về bản dịch:\n\n{text}"

    # ── Acquire semaphore — giới hạn concurrent OpenAI calls ──
    acquired = _semaphore.acquire(blocking=True, timeout=30)
    if not acquired:
        logger.warning(f"[{rid}] Semaphore timeout — server đang quá tải")
        return jsonify({"error": "Server đang xử lý quá nhiều request, vui lòng thử lại sau vài giây"}), 503

    try:
        client = get_client()

        def call_gpt(model_name: str) -> str:
            """Gọi OpenAI với timeout cứng 25 giây.
            Tự động xử lý khác biệt giữa reasoning model (gpt-5, gpt-5-mini...)
            và chat model thông thường (gpt-4.1-mini, gpt-5-chat-latest...).
            """
            logger.info(f"[{rid}] Calling {model_name} | target={target} | len={len(text)}")

            # Reasoning models (gpt-5, gpt-5-mini, gpt-5-nano, o-series...)
            # → dùng max_completion_tokens, KHÔNG nhận temperature tùy chỉnh
            is_reasoning = (
                model_name.startswith("gpt-5") and "chat" not in model_name
                or model_name.startswith("o1")
                or model_name.startswith("o3")
                or model_name.startswith("o4")
            )

            kwargs = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": build_system_prompt(target)},
                    {"role": "user",   "content": user_prompt}
                ],
                "timeout": 25
            }

            if is_reasoning:
                # Reasoning model: dùng max_completion_tokens, không set temperature
                kwargs["max_completion_tokens"] = 1024
            else:
                # Chat model thông thường: dùng max_tokens + temperature
                kwargs["max_tokens"]   = 1024
                kwargs["temperature"]  = 0

            response = client.chat.completions.create(**kwargs)
            result = response.choices[0].message.content
            if not result:
                raise RuntimeError("Empty response from model")
            return result.strip()

        # Lần 1: gpt-5-mini — nhanh, chất lượng tốt
        result = call_gpt("gpt-5-mini")

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
                logger.warning(f"[{rid}] Quality fail (mini): {error_msg} — retry với gpt-5")

                # Retry với gpt-5 — mạnh hơn
                result = call_gpt("gpt-5")
                if placeholder_map:
                    result = restore_placeholders(result, placeholder_map)

                is_valid, error_msg = validate_vi_to_zh_quality(result, original_text)
                if not is_valid:
                    logger.warning(f"[{rid}] Quality fail (gpt-5): {error_msg}")
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
