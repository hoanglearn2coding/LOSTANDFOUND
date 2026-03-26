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

# ===== 1. CẤU HÌNH (THAY THẾ TẠI ĐÂY) =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")
if not BOT_TOKEN:
    raise Exception("❌ Thiếu BOT_TOKEN")
if not API_KEY:
    raise Exception("❌ Thiếu API_KEY")
DATA_FILE = "promax_bot_data.json"
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

# ===== 3. HÀM TRỢ GIÚP API =====
async def get_api(url):
    try:
        res = await client.get(url)
        return res.json().get("response", [])
    except: return []

async def build_match_keyboard(matches_list):
    keyboard = []
    for m in matches_list[:12]:
        fid = m['fixture']['id']
        t = datetime.fromisoformat(m['fixture']['date'].replace("Z", "+00:00")).astimezone(VN_TZ).strftime("%H:%M")
        btn_text = f"Pick {t} | {m['teams']['home']['name']} - {m['teams']['away']['name']}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"pick_{fid}")])
    return InlineKeyboardMarkup(keyboard)

# ===== 4. NHÓM LỆNH TASK (NHẮC VIỆC) =====
async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state["chat_id"] = update.effective_chat.id
    try:
        time_str, content = context.args[0], " ".join(context.args[1:])
        state["tasks"].append({
            "time": time_str, "content": content, "reminded": False, 
            "note": "", "date": datetime.now(VN_TZ).strftime("%Y-%m-%d")
        })
        save_data(); await update.message.reply_text(f"✅ Đã thêm việc: {time_str}")
    except: await update.message.reply_text("❌ HD: `/add 08:00 Đi họp`")

async def tnote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        idx = int(context.args[0]) - 1
        state["tasks"][idx]["note"] = " ".join(context.args[1:])
        save_data(); await update.message.reply_text(f"📝 Đã lưu note cho Task {idx+1}")
    except: await update.message.reply_text("❌ HD: `/tnote 1 Nội dung`")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not state["tasks"]: return await update.message.reply_text("📭 Trống.")
    res = "📋 **DANH SÁCH TASK:**\n"
    for i, t in enumerate(state["tasks"]):
        res += f"{i+1}. {t['time']} - {t['content']}\n"
        if t["note"]: res += f"   └ 📝: _{t['note']}_\n"
    await update.message.reply_text(res, parse_mode="Markdown")

# ===== 5. NHÓM LỆNH BÓNG ĐÁ =====
async def matches_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
    data = await get_api(f"https://v3.football.api-sports.io/fixtures?date={today}")
    if not data: return await update.message.reply_text("📭 Không có trận.")
    await update.message.reply_text("⚽ Lịch hôm nay:", reply_markup=await build_match_keyboard(data))

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("❌ Cú pháp: `/search Tên_Đội`")
    query = " ".join(context.args).lower()
    today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
    data = await get_api(f"https://v3.football.api-sports.io/fixtures?date={today}")
    results = [m for m in data if query in m['teams']['home']['name'].lower() or query in m['teams']['away']['name'].lower()]
    if not results: return await update.message.reply_text("ℹ️ Không tìm thấy.")
    await update.message.reply_text(f"🔍 Kết quả cho '{query}':", reply_markup=await build_match_keyboard(results))

async def mnote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
        idx = int(context.args[0]) - 1
        state["boards"][today][idx]["note"] = " ".join(context.args[1:])
        save_data(); await update.message.reply_text("📝 Đã lưu note vào Board.")
    except: await update.message.reply_text("❌ HD: `/mnote 1 Nội dung`")

async def board_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(VN_TZ).strftime("%Y-%m-%d")
    matches = state["boards"].get(today, [])
    if not matches: return await update.message.reply_text("📭 Board hôm nay trống.")
    res = f"📊 **BOARD {today}:**\n\n"
    for i, m in enumerate(matches):
        icon = m.get("status_icon", "⏳")
        res += f"{i+1}. {icon} {m['home']} vs {m['away']}\n"
        if m.get("note"): res += f"   └ 📝: _{m['note']}_\n"
    await update.message.reply_text(res, parse_mode="Markdown")

# ===== 6. XỬ LÝ CALLBACK (PICK & RATE) =====
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    today = datetime.now(VN_TZ).strftime("%Y-%m-%d")

    if data.startswith("pick_"):
        fid = int(data.split("_")[1])
        state["boards"].setdefault(today, [])
        if any(x['id'] == fid for x in state["boards"][today]):
            return await query.answer("⚠️ Đã pick rồi!", show_alert=True)
        
        res = await get_api(f"https://v3.football.api-sports.io/fixtures?id={fid}")
        if res:
            m = res[0]
            state["boards"][today].append({
                "id": fid, "home": m["teams"]["home"]["name"], "away": m["teams"]["away"]["name"],
                "time": m["fixture"]["date"], "status_icon": "⏳", "note": "", "notified": False
            })
            save_data(); await query.edit_message_text(f"✅ Đã thêm: {m['teams']['home']['name']} vs {m['teams']['away']['name']}")

    elif data.startswith("rate_"):
        _, res_type, fid = data.split("_")
        icon = "✅" if res_type == "win" else "❌"
        for d in state["boards"]:
            for m in state["boards"][d]:
                if m["id"] == int(fid): m["status_icon"] = icon
        save_data(); await query.edit_message_text(f"{icon} Đã đánh giá trận đấu.")

# ===== 7. MONITOR TỰ ĐỘNG (NHẮC HẸN & BÁO KẾT QUẢ) =====
async def auto_monitor(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(VN_TZ)
    today = now.strftime("%Y-%m-%d")
    if not state["chat_id"]: return

    # Nhắc Task & Match 15p
    for t in state["tasks"]:
        if not t["reminded"] and t["date"] == today:
            target = datetime.strptime(t["time"], "%H:%M").replace(year=now.year, month=now.month, day=now.day, tzinfo=VN_TZ)
            if now >= (target - timedelta(minutes=15)) and now < target:
                await context.bot.send_message(state["chat_id"], f"⏰ **NHẮC VIỆC:** {t['content']}")
                t["reminded"] = True; save_data()

    # Kiểm tra kết quả trận đấu trong Board
    if today in state["boards"]:
        for m in state["boards"][today]:
            if not m.get("notified"):
                res = await get_api(f"https://v3.football.api-sports.io/fixtures?id={m['id']}")
                if res and res[0]["fixture"]["status"]["short"] in ["FT", "AET", "PEN"]:
                    f = res[0]
                    score = f"{f['goals']['home']}-{f['goals']['away']}"
                    kb = [[InlineKeyboardButton("✅ THẮNG", callback_data=f"rate_win_{m['id']}"),
                           InlineKeyboardButton("❌ THUA", callback_data=f"rate_loss_{m['id']}")]]
                    await context.bot.send_message(state["chat_id"], f"🏁 **KẾT THÚC:** {m['home']} {score} {m['away']}", reply_markup=InlineKeyboardMarkup(kb))
                    m["notified"] = True; save_data()

# ===== 8. KHỞI CHẠY =====
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🚀 **COMMAND LIST:**
/add [Giờ] [Việc] - Thêm Task
/tnote [STT] [Ghi chú] - Ghi chú Task
/list - Xem Task

/matches - Lịch & Pick
/search [Tên] - Tìm & Pick
/mnote [STT] [Ghi chú] - Ghi chú Board
/board - Xem Board & Kết quả
    """, parse_mode="Markdown")

def main():
    load_data()
    app = ApplicationBuilder().token(BOT_TOKEN).defaults(Defaults(tzinfo=VN_TZ)).build()
    app.add_handler(CommandHandler("start", help_cmd))
    app.add_handler(CommandHandler("add", add_task))
    app.add_handler(CommandHandler("tnote", tnote_cmd))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("matches", matches_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("mnote", mnote_cmd))
    app.add_handler(CommandHandler("board", board_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    if app.job_queue:
        app.job_queue.run_repeating(auto_monitor, interval=120, first=10)

    print("✅ BOT PRO MAX FINAL ONLINE!"); app.run_polling()

if __name__ == "__main__": main()