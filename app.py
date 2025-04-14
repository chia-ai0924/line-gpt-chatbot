from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from deep_translator import GoogleTranslator
import openai
import os
import requests
import logging

app = Flask(__name__)

# 設定 log 輸出
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# 環境變數
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")

@app.route("/", methods=["GET"])
def index():
    return {"status": "Chatbot is running"}

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    logger.info("📥 收到 LINE Webhook 請求")
    logger.info(f"📦 Headers: {request.headers}")
    logger.info(f"📨 Body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("❌ 簽名驗證失敗")
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    try:
        user_message = event.message.text
        logger.info(f"📨 收到文字訊息: {user_message}")

        gpt_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": user_message}]
        )

        reply = gpt_response["choices"][0]["message"]["content"]
        logger.info(f"🤖 回覆訊息: {reply}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        logger.error(f"❌ 回覆文字訊息時錯誤: {str(e)}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="發生錯誤，請稍後再試。"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        logger.info("🖼️ 收到圖片訊息，開始處理圖片...")

        # 下載圖片
        image_content = line_bot_api.get_message_content(event.message.id)
        image_path = f"/tmp/{event.message.id}.jpg"
        with open(image_path, "wb") as f:
            for chunk in image_content.iter_content():
                f.write(chunk)

        logger.info(f"✅ 圖片下載成功: {image_path}")

        # 上傳至 OCR API
        with open(image_path, "rb") as f:
            res = requests.post(
                "https://api.ocr.space/parse/image",
                files={"file": f},
                data={"language": "eng", "isOverlayRequired": False},
                headers={"apikey": ocr_api_key}
            )

        result = res.json()
        text = result["ParsedResults"][0]["ParsedText"]
        logger.info(f"🔍 OCR 辨識結果: {text}")

        if not text.strip():
            reply = "我沒有在圖片中辨識到文字喔。"
        else:
            try:
                translated = GoogleTranslator(source="auto", target="zh-tw").translate(text)
                logger.info(f"🌐 翻譯為中文: {translated}")
            except Exception as e:
                logger.warning(f"🌐 翻譯時錯誤，跳過翻譯: {str(e)}")
                translated = text

            # 傳給 GPT 理解
            gpt_response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "你是一個能幫助使用者解釋圖片中文字的 AI 助手。"},
                    {"role": "user", "content": translated}
                ]
            )
            reply = gpt_response["choices"][0]["message"]["content"]

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        logger.error(f"❌ 處理圖片時發生錯誤: {str(e)}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="處理圖片時發生錯誤，請稍後再試。"))

