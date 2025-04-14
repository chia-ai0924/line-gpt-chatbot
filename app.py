from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
from deep_translator import GoogleTranslator
import openai

app = Flask(__name__)

# LINE & OpenAI 設定
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")

# 測試首頁
@app.route("/", methods=["GET"])
def index():
    return {"status": "Chatbot is running"}

# ✅ 關鍵修正：加入正確的 callback 路由
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("LINE webhook error:", e)
        abort(400)
    return 'OK'

# 文字訊息事件處理
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_text = event.message.text
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_text}]
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        reply = f"發生錯誤：{str(e)}"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

# 圖片訊息事件處理
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        message_content = line_bot_api.get_message_content(event.message.id)
        with open("temp.jpg", "wb") as f:
            for chunk in message_content.iter_content():
                f.write(chunk)
        with open("temp.jpg", "rb") as image_file:
            response = requests.post(
                "https://api.ocr.space/parse/image",
                files={"filename": image_file},
                data={"apikey": ocr_api_key, "language": "eng"}
            )
        result = response.json()
        text = result["ParsedResults"][0]["ParsedText"]
        if not text.strip():
            reply = "圖片中沒有識別到任何文字。"
        else:
            translated = GoogleTranslator(source='auto', target='zh-tw').translate(text)
            reply = f"🔍 圖片辨識結果：\n{text}\n\n🌐 翻譯結果：\n{translated}"
    except Exception as e:
        reply = f"圖片處理失敗：{str(e)}"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

# 執行應用（Render 用 gunicorn，不需要啟動 app.run）

