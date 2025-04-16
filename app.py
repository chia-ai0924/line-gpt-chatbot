import os
import uuid
import shutil
import logging
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from openai import OpenAI
from PIL import Image
import pytesseract
import requests
import threading
from langdetect import detect
from deep_translator import GoogleTranslator

# 初始化
app = Flask(__name__, static_url_path='/image', static_folder='static/images')
client = OpenAI()
logging.basicConfig(level=logging.INFO)

# 設定你的環境變數
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# 確保 static/images 資料夾存在
os.makedirs("static/images", exist_ok=True)

def remove_file_later(filepath, delay=180):
    def delete():
        import time
        time.sleep(delay)
        try:
            os.remove(filepath)
        except Exception as e:
            logging.warning(f"刪除圖片失敗：{e}")
    threading.Thread(target=delete).start()

def generate_token():
    import secrets
    return secrets.token_hex(8)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        logging.error(f"LINE 處理失敗: {e}")
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        message_id = event.message.id
        ext = "jpg"
        token = generate_token()
        filename = f"{uuid.uuid4()}.{ext}"
        filepath = os.path.join("static/images", filename)

        # 儲存圖片
        content = line_bot_api.get_message_content(message_id)
        with open(filepath, "wb") as f:
            for chunk in content.iter_content():
                f.write(chunk)
        logging.info("圖片下載成功")

        # OCR 辨識
        image = Image.open(filepath)
        ocr_text = pytesseract.image_to_string(image, lang="eng+chi_tra").strip()
        logging.info(f"OCR 辨識結果: {ocr_text}")

        if ocr_text:
            lang = detect(ocr_text)
            if lang != "zh-tw":
                translated = GoogleTranslator(source='auto', target='zh-tw').translate(ocr_text)
            else:
                translated = ocr_text
            prompt = f"這張圖片中的文字內容是：{translated}。請根據這些文字給我一段有幫助的說明。"
        else:
            prompt = f"這是一張圖片，請你根據圖片內容進行分析與說明。若為菜單請翻譯、若為表格請整理。圖片網址為：https://line-gpt-chatbot-fiv0.onrender.com/image/{filename}?auth={token}"

        # GPT Vision 處理
        with open(filepath, "rb") as f:
            gpt_response = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"https://line-gpt-chatbot-fiv0.onrender.com/image/{filename}?auth={token}"
                        }}
                    ]}
                ],
                max_tokens=1000
            )
        final_reply = gpt_response.choices[0].message.content.strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=final_reply))

        # 三分鐘後自動刪除
        remove_file_later(filepath)

        # 儲存 token 驗證（簡化版，實作中未查驗 token，有需要再加強）
    except Exception as e:
        logging.error("圖片處理錯誤", exc_info=True)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="圖片處理時發生錯誤，請稍後再試。"))

@app.route("/")
def home():
    return "Line GPT Bot is running."

if __name__ == "__main__":
    app.run()
