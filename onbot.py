import os
import json
import logging
import httpx
import pytz
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, 
    CallbackQueryHandler, Defaults
)

# ===== 1. CẤU HÌNH (LẤY TỪ RAILWAY VARIABLES) =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")
if not BOT_TOKEN:
    raise Exception("❌ Thiếu BOT_TOKEN")
if not API_KEY:
    raise Exception("❌ Thiếu API_KEY")
DATA_FILE = "premium_bot_data.json"
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# ===== 2. QUẢN LÝ DỮ LIỆU =====
state = {"tasks": [], "boards": {}, "chat_id": None}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            state.update(json.load(f))

client = httpx.AsyncClient(headers={"x-apisports-key": API_KEY}, timeout=20)

# ===== 3. MENU CHÀO MỪNG (THEO PHONG CÁCH NHÀ HÀNG) =====
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state["chat_id"] = update.effective_chat.id
    menu_text = (
        "🏠 **CHÀO MỪNG BẠN ĐẾN VỚI FOOTBALL & TASK MANAGER**\n"
        "*Vui lòng chọn 'món ăn' bạn muốn sử dụng dưới đây:*\n\n"
        "🧠 **[ MỤC NHẮC VIỆC - TASK ]**\n"
        " ├ `/add [Giờ] [Việc]` : Thêm món việc mới\n"
        " ├ `/list` : Xem thực đơn công việc\n"
        " └ `/tnote [STT] [Ghi chú]` : Thêm gia vị cho việc\n\n"
        "⚽ **[ MỤC TRẬN ĐẤU - FOOTBALL ]**\n"
        " ├ `/matches` : Xem lịch thi đấu hôm nay\n"
        " ├ `/search [Tên]` : Tìm trận đấu theo yêu cầu\n"
        " ├ `/board` : Bảng theo dõi các trận đã chọn\n"
        " └ `/mnote [STT] [Ghi chú]` : Chú thích chiến thuật\n\n"
        "ℹ️ *Gợi ý: Sau khi Add hoặc Pick, tôi sẽ hỏi bạn có muốn thêm ghi chú ngay không!*"
    )
    await update.message.reply_text(menu_text, parse_mode="Markdown")

# ===== 4. XỬ LÝ TASK & NHẮC VIỆC =====
async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        time_str, content = context.args[0], " ".join(context.args[1:])
        new_task = {
            "time": time_str, "content": content, "reminded": False, 
            "note": "", "date": datetime.now(VN_TZ).strftime("%Y-%m-%d")
        }
        state["tasks"].append(new_task)
        save_data()
        
        # Hỏi dùng Note ngay
        idx = len(state["tasks"])
        kb = [[InlineKeyboardButton("📝 Thêm ghi chú ngay", callback_data=f"asknote_t_{idx}")]]
        await update.message.reply_text(f"✅ Đã thêm việc: {content}", reply_markup=InlineKeyboardMarkup(kb))
    except:
        await update.message.reply_text("❌ Cú pháp: `/add 08:00 Đi họp`")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not state["tasks"]: return await update.message.reply_text("📭 Danh sách trống.")
    res = "📋 **THỰC ĐƠN CÔNG VIỆC:**\n"
    for i, t in enumerate(state["tasks"]):
        res += f"{i+1}. 🕒 {t['time']} - *{t['content']}*\n"
        if t["note"]: res += f"   └ 💡: _{t['note']}_\n"
    await update.message.reply_text(res, parse_mode="Markdown")

# ===== 5. XỬ LÝ BÓNG ĐÁ =====
async def get_matches(date_str):
    url = f"https://v3.football.api-sports.io/fixtures?date={date_str}"
    try:
        res = await client.get(url)
        return res.json().get("response", [])
    except: return []

async def matches_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
    data = await get_matches(today)
    if not data: return await update.message.reply_text("📭 Không có trận.")
    
    kb = []
    for m in data[:12]:
        fid = m['fixture']['id']
        t = datetime.fromisoformat(m['fixture']['date'].replace("Z", "+00:00")).astimezone(VN_TZ).strftime("%H:%M")
        btn_text = f"⚽ {t} | {m['teams']['home']['name']} - {m['teams']['away']['name']}"
        kb.append([InlineKeyboardButton(btn_text, callback_data=f"pk_{fid}")])
    await update.message.reply_text("⚽ **CHỌN TRẬN ĐẤU CỦA BẠN:**", reply_markup=InlineKeyboardMarkup(kb))

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("❌ Nhập tên đội: `/search MU`")
    query = " ".join(context.args).lower()
    data = await get_matches(datetime.now(VN_TZ).strftime("%Y-%m-%d"))
    res = [m for m in data if query in m['teams']['home']['name'].lower() or query in m['teams']['away']['name'].lower()]
    
    if not res: return await update.message.reply_text("ℹ️ Không tìm thấy.")
    kb = []
    for m in res[:10]:
        fid = m['fixture']['id']
        t = datetime.fromisoformat(m['fixture']['date'].replace("Z", "+00:00")).astimezone(VN_TZ).strftime("%H:%M")
        kb.append([InlineKeyboardButton(f"⚽ {t} | {m['teams']['home']['name']}", callback_data=f"pk_{fid}")])
    await update.message.reply_text(f"🔍 Kết quả cho '{query}':", reply_markup=InlineKeyboardMarkup(kb))

async def board_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
    matches = state["boards"].get(today, [])
    if not matches: return await update.message.reply_text("📭 Board trống.")
    res = f"📊 **BẢNG THEO DÕI {today}:**\n\n"
    for i, m in enumerate(matches):
        icon = m.get("status_icon", "⏳")
        res += f"{i+1}. {icon} *{m['home']} vs {m['away']}*\n"
        if m.get("note"): res += f"   └ 💡: _{m['note']}_\n"
    await update.message.reply_text(res, parse_mode="Markdown")

# ===== 6. CALLBACK HANDLER (PICK & ASKING NOTE) =====
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    today = datetime.now(VN_TZ).strftime("%Y-%m-%d")

    # Pick trận
    if data.startswith("pk_"):
        fid = int(data.split("_")[1])
        state["boards"].setdefault(today, [])
        if any(x['id'] == fid for x in state["boards"][today]):
            return await query.answer("⚠️ Đã pick!", show_alert=True)
        
        res = await client.get(f"https://v3.football.api-sports.io/fixtures?id={fid}")
        m = res.json()["response"][0]
        state["boards"][today].append({
            "id": fid, "home": m["teams"]["home"]["name"], "away": m["teams"]["away"]["name"],
            "time": m["fixture"]["date"], "status_icon": "⏳", "note": "", "notified": False
        })
        save_data()
        
        idx = len(state["boards"][today])
        kb = [[InlineKeyboardButton("📝 Thêm ghi chú trận đấu", callback_data=f"asknote_m_{idx}")]]
        await query.edit_message_text(f"✅ Đã chọn: {m['teams']['home']['name']} vs {m['teams']['away']['name']}", reply_markup=InlineKeyboardMarkup(kb))

    # Hướng dẫn thêm Note ngay
    elif data.startswith("asknote_"):
        _, kind, idx = data.split("_")
        cmd = "/tnote" if kind == "t" else "/mnote"
        await query.message.reply_text(f"👉 Để thêm ghi chú cho món này, hãy gõ:\n`{cmd} {idx} Nội dung ghi chú của bạn`", parse_mode="Markdown")
        await query.answer()

# ===== 7. LỆNH GHI CHÚ (NOTE) =====
async def tnote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        idx = int(context.args[0]) - 1
        state["tasks"][idx]["note"] = " ".join(context.args[1:])
        save_data(); await update.message.reply_text(f"📝 Ghi chú task {idx+1} thành công!")
    except: await update.message.reply_text("❌ HD: `/tnote 1 Nội dung`")

async def mnote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
        idx = int(context.args[0]) - 1
        state["boards"][today][idx]["note"] = " ".join(context.args[1:])
        save_data(); await update.message.reply_text(f"📝 Ghi chú trận {idx+1} thành công!")
    except: await update.message.reply_text("❌ HD: `/mnote 1 Nội dung`")

# ===== 8. MONITOR TỰ ĐỘNG (15P & KẾT QUẢ) =====
async def auto_monitor(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(VN_TZ)
    today = now.strftime("%Y-%m-%d")
    if not state["chat_id"]: return

    # Nhắc 15p Task
    for t in state["tasks"]:
        if not t["reminded"] and t["date"] == today:
            target = datetime.strptime(t["time"], "%H:%M").replace(year=now.year, month=now.month, day=now.day, tzinfo=VN_TZ)
            if now >= (target - timedelta(minutes=15)) and now < target:
                msg = f"⏰ **NHẮC VIỆC (15p nữa):**\n{t['content']}"
                if t['note']: msg += f"\n💡 Chú ý: {t['note']}"
                await context.bot.send_message(state["chat_id"], msg)
                t["reminded"] = True; save_data()

    # Báo kết quả khi hết trận
    if today in state["boards"]:
        for m in state["boards"][today]:
            if not m.get("notified"):
                res = await client.get(f"https://v3.football.api-sports.io/fixtures?id={m['id']}")
                f = res.json()["response"][0]
                if f["fixture"]["status"]["short"] in ["FT", "AET", "PEN"]:
                    score = f"{f['goals']['home']}-{f['goals']['away']}"
                    await context.bot.send_message(state["chat_id"], f"🏁 **HẾT GIỜ:** {m['home']} {score} {m['away']}")
                    m["notified"] = True; save_data()

# ===== 9. MAIN =====
def main():
    load_data()
    app = ApplicationBuilder().token(BOT_TOKEN).defaults(Defaults(tzinfo=VN_TZ)).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", start_cmd))
    app.add_handler(CommandHandler("add", add_task))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("tnote", tnote_cmd))
    app.add_handler(CommandHandler("matches", matches_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("mnote", mnote_cmd))
    app.add_handler(CommandHandler("board", board_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))

    if app.job_queue:
        app.job_queue.run_repeating(auto_monitor, interval=120, first=10)

    print("🚀 BOT PREMIUM MENU IS LIVE!"); app.run_polling()

if __name__ == "__main__": main()