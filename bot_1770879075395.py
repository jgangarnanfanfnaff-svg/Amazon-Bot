import logging
import re
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler
import json
import threading
from flask import Flask
import os
from PIL import Image
from io import BytesIO

app = Flask('')
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/')
def home():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=8080, debug=False)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)
logger = logging.getLogger(__name__)

TOKEN = "8379787913:AAEDXdcelMNbaRKOcybfB_bjN2yGg4wdAYI"
OWNER_USERNAME = "Noor43446"
CONFIG_FILE = "config.json"
BUNDLE_TITLE, BUNDLE_LINKS = range(2)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: return json.load(f)
        except: return {"target_channel": ""}
    return {"target_channel": ""}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f: json.dump(config, f)

def get_product_info(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ar-SA,ar;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    try:
        original_input_url = url
        session = requests.Session()
        response = session.get(url, headers=headers, allow_redirects=True, timeout=15)
        if response.status_code != 200: return None
        
        soup = BeautifulSoup(response.content, "lxml")
        
        title_tag = soup.find("span", {"id": "productTitle"})
        name = title_tag.get_text().strip() if title_tag else "منتج أمازون"

        price = None
        price_span = soup.find("span", {"class": "a-price-whole"})
        if price_span:
            try: 
                price_text = price_span.get_text().replace(',', '').replace('ر.س', '').strip()
                price = float(re.sub(r'[^\d.]', '', price_text))
            except: pass
        
        if not price:
            price_meta = soup.find("span", {"class": "a-offscreen"})
            if price_meta:
                try: 
                    price_text = price_meta.get_text().replace('ر.س', '').strip()
                    price = float(re.sub(r'[^\d.]', '', price_text))
                except: pass
        
        if not price:
            for span in soup.find_all("span"):
                try:
                    price_text = span.get_text().strip()
                    if 'ر.س' in price_text or re.search(r'\d+\.\d+', price_text):
                        price_val = float(re.sub(r'[^\d.]', '', price_text))
                        if price_val > 0:
                            price = price_val
                            break
                except: pass

        image = None
        img_tag = soup.find("img", {"id": "landingImage"}) or soup.find("img", {"id": "imgBlkFront"})
        if img_tag:
            dyn_img = img_tag.get("data-a-dynamic-image")
            if dyn_img:
                try: 
                    img_dict = json.loads(dyn_img)
                    if img_dict: image = list(img_dict.keys())[-1]
                except: image = img_tag.get("src")
            else: image = img_tag.get("src")
        
        return {"name": name, "original_price": price, "image": image, "url": original_input_url}
    except: return None

def format_price(original_price):
    if not original_price: return "---"
    raw_discounted = original_price * 0.60
    final_price = (int(raw_discounted * 10) / 10.0)
    return f"{final_price:.0f}" if final_price == int(final_price) else f"{final_price:.1f}"

def create_collage(image_urls):
    images = []
    for url in image_urls[:4]:
        try:
            resp = requests.get(url, timeout=10)
            img = Image.open(BytesIO(resp.content))
            if img.mode != 'RGB': img = img.convert('RGB')
            img.thumbnail((400, 400))
            images.append(img)
        except: continue
    
    if not images: return None
    
    n = len(images)
    cols = 2 if n > 1 else 1
    rows = (n + 1) // 2
    
    w, h = 400, 400
    collage = Image.new('RGB', (cols * w, rows * h), (255, 255, 255))
    
    for i, img in enumerate(images):
        x, y = (i % cols) * w, (i // cols) * h
        collage.paste(img, (x + (w - img.width) // 2, y + (h - img.height) // 2))
    
    bio = BytesIO()
    collage.save(bio, 'JPEG', quality=85)
    bio.seek(0)
    return bio

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME: return
    
    welcome_text = (
        "👋 <b>أهلاً بك في بوت قناص عروض أمازون المطور!</b>\n\n"
        "هذا البوت مصمم لمساعدتك في تجهيز عروض أمازون ونشرها في قناتك بلمح البصر.\n\n"
        "🛠 <b>الأوامر المتاحة:</b>\n\n"
        "1️⃣ <b>العرض الفردي:</b>\n"
        "فقط أرسل رابط المنتج (أو شاركه من تطبيق أمازون) وسيقوم البوت بسحب الصورة والاسم وحساب السعر بعد خصم 40% تلقائياً.\n\n"
        "2️⃣ <b>وضع المجمع (Bundle):</b>\n"
        "استخدم أمر /bundle لتجميع عدة منتجات في رسالة واحدة. \n"
        "• أرسل العنوان (مثلاً: عروض الأرز).\n"
        "• أرسل الروابط واحداً تلو الآخر.\n"
        "• أرسل /done عند الانتهاء.\n"
        "• <b>جديد:</b> سيقوم البوت بدمج صور المنتجات في صورة واحدة!\n\n"
        "3️⃣ <b>إعدادات القناة:</b>\n"
        "استخدم /set_channel @اسم_القناة لتحديد القناة التي سيتم النشر فيها.\n\n"
        "📢 <b>القناة الحالية:</b> <code>" + load_config().get("target_channel", "لم تحدد بعد") + "</code>"
    )
    
    keyboard = [
        [InlineKeyboardButton("📦 بدء وضع المجمع", callback_data='start_bundle')],
        [InlineKeyboardButton("⚙️ ضبط القناة", callback_data='show_channel_help')]
    ]
    
    await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME: return
    if not context.args:
        await update.message.reply_text("❌ مثال: /set_channel @Strongoffers1")
        return
    channel = context.args[0]
    config = load_config()
    config["target_channel"] = channel
    save_config(config)
    await update.message.reply_text(f"✅ تم تحديد القناة: <b>{channel}</b>", parse_mode='HTML')

async def bundle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME: return ConversationHandler.END
    await update.message.reply_text("📦 <b>بدء وضع المجمع</b>\nأرسل العنوان الرئيسي للعروض (مثلاً: عروض الأرز):", parse_mode='HTML')
    return BUNDLE_TITLE

async def bundle_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['bundle_title'] = update.message.text
    context.user_data['bundle_items'] = []
    await update.message.reply_text(f"✅ العنوان: <b>{update.message.text}</b>\nالآن أرسل روابط المنتجات واحداً تلو الآخر. عند الانتهاء أرسل /done", parse_mode='HTML')
    return BUNDLE_LINKS

async def bundle_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url_match = re.search(r'https?://[^\s]+', update.message.text)
    if not url_match:
        await update.message.reply_text("❌ يرجى إرسال رابط صحيح أو /done للإنهاء.")
        return BUNDLE_LINKS
    
    url = url_match.group(0)
    wait_msg = await update.message.reply_text("⏳ جاري جلب بيانات المنتج...")
    info = get_product_info(url)
    await wait_msg.delete()
    
    if info:
        context.user_data['bundle_items'].append(info)
        await update.message.reply_text(f"✅ تم إضافة: {info['name'][:30]}...\nأرسل الرابط التالي أو /done للإنهاء.")
    else:
        await update.message.reply_text("❌ فشل جلب هذا المنتج، جرب رابطاً آخر.")
    return BUNDLE_LINKS

async def bundle_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = context.user_data.get('bundle_title', 'عروض مميزة')
    items = context.user_data.get('bundle_items', [])
    
    if not items:
        await update.message.reply_text("❌ لم يتم إضافة أي روابط. تم إلغاء العملية.")
        return ConversationHandler.END
    
    msg = f"<b>{title}</b>\n\n"
    image_urls = []
    for item in items:
        price = format_price(item['original_price'])
        msg += f"{item['name']}\n<b>بسعر {price} ريال بس</b> 🔥\n\nالرابط:\n{item['url']}\n\n\n"
        if item['image']: image_urls.append(item['image'])
    
    msg += "✅ استخدام كود خصم المؤثرين 15%\n\n✅ فعل خصم بطاقة مدى بنك الرياض (مجانية) 25%\n\nالحد الأدنى للطلب 100 ريال عشان يتفعل الخصم"
    
    context.user_data['pending_msg'] = msg
    
    collage_bio = None
    if image_urls:
        wait_msg = await update.message.reply_text("🎨 جاري دمج الصور...")
        collage_bio = create_collage(image_urls)
        await wait_msg.delete()
    
    context.user_data['pending_img'] = collage_bio
    
    keyboard = [[InlineKeyboardButton("نشر في القناة ✅", callback_data='publish')],
                [InlineKeyboardButton("إلغاء ❌", callback_data='cancel')]]
    
    if collage_bio:
        await update.message.reply_photo(photo=collage_bio, caption=msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    
    return ConversationHandler.END

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME: return
    url_match = re.search(r'https?://[^\s]+', update.message.text)
    if not url_match: return
    
    url = url_match.group(0)
    wait_msg = await update.message.reply_text("⏳ جاري جلب البيانات...")
    info = get_product_info(url)
    await wait_msg.delete()
    
    if not info:
        await update.message.reply_text("❌ فشل جلب البيانات.")
        return
    
    price = format_price(info['original_price'])
    msg = (
        f"<b>{info['name']}</b>\n\n"
        f"<b>بسعر {price} ريال تقريبًا بس</b> 🔥\n\n"
        f"الرابط: {url}\n\n"
        f"✅ استخدام كود خصم المؤثرين 15%\n\n"
        f"✅ فعل خصم بطاقة مدى بنك الرياض 25%\n\n"
        f"الحد الأدنى للطلب 100 ريال عشان يتفعل الخصم\n\n"
        f"أي سؤال تفضل ⬇️"
    )
    
    context.user_data['pending_msg'] = msg
    context.user_data['pending_img_url'] = info['image']
    
    keyboard = [[InlineKeyboardButton("نشر في القناة ✅", callback_data='publish')],
                [InlineKeyboardButton("إلغاء ❌", callback_data='cancel')]]
    
    if info['image']:
        await update.message.reply_photo(photo=info['image'], caption=msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text=msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'publish':
        config = load_config()
        channel = config.get("target_channel")
        if not channel:
            await query.message.reply_text("⚠️ حدد قناة أولاً: /set_channel")
            return
        
        msg = context.user_data.get('pending_msg')
        img = context.user_data.get('pending_img')
        img_url = context.user_data.get('pending_img_url')
        
        try:
            if img:
                img.seek(0)
                await context.bot.send_photo(chat_id=channel, photo=img, caption=msg, parse_mode='HTML')
            elif img_url:
                await context.bot.send_photo(chat_id=channel, photo=img_url, caption=msg, parse_mode='HTML')
            else:
                await context.bot.send_message(chat_id=channel, text=msg, parse_mode='HTML')
            
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("✅ تم النشر بنجاح!")
        except Exception as e:
            await query.message.reply_text(f"❌ فشل النشر: {e}")
    elif query.data == 'cancel': await query.message.delete()
    elif query.data == 'start_bundle':
        await query.message.reply_text("📦 <b>بدء وضع المجمع</b>\nأرسل العنوان الرئيسي للعروض (مثلاً: عروض الأرز):", parse_mode='HTML')
    elif query.data == 'show_channel_help':
        await query.message.reply_text("⚙️ <b>طريقة ضبط القناة:</b>\nأرسل الأمر كالتالي:\n<code>/set_channel @Strongoffers1</code>", parse_mode='HTML')

def main():
    threading.Thread(target=run_flask).start()
    application = Application.builder().token(TOKEN).build()
    
    bundle_handler = ConversationHandler(
        entry_points=[CommandHandler("bundle", bundle_start)],
        states={
            BUNDLE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bundle_title)],
            BUNDLE_LINKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, bundle_links), CommandHandler("done", bundle_done)],
        },
        fallbacks=[CommandHandler("done", bundle_done)],
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("set_channel", set_channel))
    application.add_handler(bundle_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
