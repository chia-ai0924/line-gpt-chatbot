from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
from deep_translator import GoogleTranslator
import openai
import logging
from openai import OpenAI
from io import BytesIO

# Logging 設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = Flask(__name__)

# 初始化 LINE Bot
line_bot_api = LineBotApi(os.getenv("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 初始化 OpenAI client (v1)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# OCR API Key
ocr_api_key = os.getenv("OCR_API_KEY")

@app.route("/", methods=["GET"])
def index():
    return {"status": "Chatbot is running"}

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    logger.info(f"收到 LINE 請求：{body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("❌ LINE 簽名驗證失敗")
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    try:
        user_text = event.message.text
        logger.info(f"🟣 收到文字訊息: {user_text}")

        # 呼叫 GPT-4 回答
        gpt_response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": user_text}]
        )

        reply_text = gpt_response.choices[0].message.content.strip()
        logger.info(f"🟢 回覆訊息: {reply_text}")

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
    except Exception as e:
        logger.error("❌ 回覆文字訊息時錯誤", exc_info=True)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="發生錯誤，請稍後再試。"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        logger.info("📥 收到圖片訊息")
        image_content = line_bot_api.get_message_content(event.message.id)
        image_bytes = BytesIO(image_content.content)

        # 發送到 OCR.Space API
        logger.info("🧠 傳送圖片至 OCR 進行辨識")
        ocr_url = "https://api.ocr.space/parse/image"
        response = requests.post(
            ocr_url,
            files={"filename": image_bytes},
            data={"language": "eng", "apikey": ocr_api_key},
        )
        result = response.json()
        parsed_text = result["ParsedResults"][0]["ParsedText"].strip()
        logger.info(f"🔍 OCR 辨識結果：{parsed_text}")

        # 翻譯為中文（如果不是中文）
        if parsed_text:
            try:
                translated_text = GoogleTranslator(source="auto", target="zh-tw").translate(parsed_text)
                logger.info(f"🌍 翻譯結果：{translated_text}")
            except Exception:
                translated_text = parsed_text
        else:
            translated_text = "無法從圖片中辨識出文字"

        # 呼叫 GPT 智能分析
        gpt_response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": f"這段文字來自圖片：{translated_text}\n請幫我分析並給出說明。"}]
        )
        reply_text = gpt_response.choices[0].message.content.strip()
        logger.info(f"🤖 GPT 分析結果：{reply_text}")

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    except Exception as e:
        logger.error("❌ 處理圖片訊息時發生錯誤", exc_info=True)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="圖片處理時發生錯誤，請稍後再試。"))


