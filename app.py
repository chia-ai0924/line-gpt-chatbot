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

# 啟用 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 讀取環境變數
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")

@app.route("/", methods=['GET'])
def index():
    return {"status": "Chatbot is running"}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    logger.info("📥 收到 LINE Webhook 請求")
    logger.info(f"📦 Headers: {dict(request.headers)}")
    logger.info(f"📝 Body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("❌ 簽章驗證失敗")
        abort(400)
    except Exception as e:
        logger.exception(f"❗ webhook 處理錯誤: {e}")
        abort(500)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    try:
        user_message = event.message.text
        logger.info(f"🗣️ 收到文字訊息: {user_message}")

        gpt_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_message}]
        )
        reply_text = gpt_response.choices[0].message.content.strip()
        logger.info(f"🤖 GPT 回覆: {reply_text}")

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
    except Exception as e:
        logger.exception("❌ 回覆文字訊息時錯誤")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="發生錯誤，請稍後再試。"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        logger.info("🖼️ 收到圖片訊息")

        # 下載圖片
        message_content = line_bot_api.get_message_content(event.message.id)
        image_data = message_content.content
        with open("temp.jpg", "wb") as f:
            f.write(image_data)
        logger.info("✅ 圖片已儲存為 temp.jpg")

        # OCR
        with open("temp.jpg", "rb") as f:
            r = requests.post(
                "https://api.ocr.space/parse/image",
                files={"filename": f},
                data={"apikey": ocr_api_key, "language": "eng"},
            )
        result = r.json()
        logger.info(f"🔍 OCR 回應: {result}")

        parsed_text = result["ParsedResults"][0]["ParsedText"].strip()

        if not parsed_text:
            reply = "圖片中無法辨識出文字。"
        else:
            # 翻譯（如需要）
            try:
                translated_text = GoogleTranslator(source='auto', target='zh-tw').translate(parsed_text)
            except Exception as e:
                logger.warning(f"⚠️ 翻譯失敗：{e}")
                translated_text = parsed_text

            logger.info(f"🈶 GPT 分析文字: {translated_text}")

            # 呼叫 GPT 回應分析
            gpt_response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{
                    "role": "user",
                    "content": f"這段內容是從圖片中辨識出來的文字：\n{translated_text}\n\n請幫我解釋它的意思，提供背景資訊或建議用途。"
                }]
            )
            reply = gpt_response.choices[0].message.content.strip()

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        logger.exception("❌ 處理圖片訊息時錯誤")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="圖片處理失敗，請稍後再試。"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
