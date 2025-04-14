from flask import Flask, request, abort
import os
import logging
import requests
import openai
from deep_translator import GoogleTranslator
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage

app = Flask(__name__)

# 設定 logging
logging.basicConfig(level=logging.INFO)

# 設定 API 金鑰
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")

@app.route("/", methods=["GET"])
def index():
    return {"status": "Chatbot is running"}

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    app.logger.info("🔥 Received /callback webhook")
    app.logger.info("📦 Body: %s", body)
    app.logger.info("🖊️ Signature: %s", signature)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.warning("⚠️ Invalid signature!")
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_message = event.message.text
    app.logger.info("🗣️ Received user text: %s", user_message)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_message}]
        )
        reply_text = response.choices[0].message.content.strip()
    except Exception as e:
        app.logger.error("❌ OpenAI Error: %s", e)
        reply_text = "發生錯誤，請稍後再試。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    app.logger.info("🖼️ Received image message")

    try:
        # 取得圖片內容
        message_content = line_bot_api.get_message_content(event.message.id)
        image_data = message_content.content

        # 上傳到 OCR.Space 進行辨識
        response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"filename": ("image.jpg", image_data)},
            data={"apikey": ocr_api_key, "language": "eng"}
        )
        result = response.json()
        app.logger.info("🔍 OCR Response: %s", result)

        parsed_text = result["ParsedResults"][0]["ParsedText"].strip()
        if not parsed_text:
            reply_text = "圖片中找不到可辨識的文字。"
        else:
            app.logger.info("🌐 Detected text: %s", parsed_text)
            # 若為非中文，自動翻譯
            try:
                translated = GoogleTranslator(source="auto", target="zh-tw").translate(parsed_text)
                reply_text = f"圖片文字：\n{parsed_text}\n\n翻譯：\n{translated}"
            except Exception as e:
                app.logger.warning("⚠️ 翻譯失敗：%s", e)
                reply_text = f"圖片文字：\n{parsed_text}"

    except Exception as e:
        app.logger.error("❌ 處理圖片時出錯：%s", e)
        reply_text = "處理圖片時發生錯誤。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
