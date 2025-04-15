from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
import openai
from deep_translator import GoogleTranslator
import logging

# 初始化
app = Flask(__name__)

# 設定 log 格式
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 讀取環境變數
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")

@app.route("/")
def home():
    return "LINE GPT Chatbot is running!"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    logger.info("🔔 收到 LINE Webhook 請求")
    logger.info(f"📦 Headers: {request.headers}")
    logger.info(f"📩 Body: {body}")
    try:
        handler.handle(body, signature)
    except Exception as e:
        logger.exception(f"❌ Webhook 處理失敗: {e}")
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_msg = event.message.text
    logger.info(f"📨 收到文字訊息: {user_msg}")
    try:
        gpt_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一個聰明且有幫助的助理，所有回覆使用繁體中文。"},
                {"role": "user", "content": user_msg}
            ]
        )
        reply_text = gpt_response.choices[0].message.content.strip()
        logger.info(f"✅ GPT 回覆成功: {reply_text}")
    except Exception as e:
        logger.exception("❌ 回覆文字訊息時錯誤:")
        reply_text = "發生錯誤，請稍後再試。"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    logger.info("🖼️ 收到圖片訊息，開始處理圖片...")
    try:
        # 下載圖片
        message_content = line_bot_api.get_message_content(event.message.id)
        image_path = f"/tmp/{event.message.id}.jpg"
        with open(image_path, 'wb') as f:
            for chunk in message_content.iter_content():
                f.write(chunk)
        logger.info(f"✅ 圖片下載成功: {image_path}")

        # 使用 OCR.Space 進行文字辨識
        with open(image_path, 'rb') as image_file:
            response = requests.post(
                "https://api.ocr.space/parse/image",
                files={"file": image_file},
                data={"apikey": ocr_api_key, "language": "eng"},
            )
        result = response.json()
        parsed_text = result["ParsedResults"][0]["ParsedText"].strip()
        logger.info(f"📖 OCR 辨識結果: {parsed_text}")

        # 判斷語言，若非中文則翻譯成繁體中文
        try:
            translated_text = GoogleTranslator(source='auto', target='zh-TW').translate(parsed_text)
            logger.info(f"🌐 翻譯後文字（繁體中文）: {translated_text}")
        except Exception as e:
            logger.warning(f"⚠️ 翻譯時發生錯誤: {e}")
            translated_text = f"辨識成功，但翻譯過程發生錯誤。原始文字：\n{parsed_text}"

        # 送到 GPT 分析
        try:
            gpt_response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "你是一個能解釋圖片中資訊的助手，請以繁體中文回覆使用者的問題。"},
                    {"role": "user", "content": f"這是圖片內的內容：\n{translated_text}\n請告訴我這是什麼，以及可能的用途或建議。"}
                ]
            )
            final_reply = gpt_response.choices[0].message.content.strip()
        except Exception as e:
            logger.exception("❌ GPT 圖片分析時發生錯誤:")
            final_reply = f"圖片內容為：\n{translated_text}"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=final_reply))
    except Exception as e:
        logger.exception("❌ 處理圖片時發生錯誤:")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="處理圖片時發生錯誤，請稍後再試。"))

# Flask 啟動設定（Render 用 gunicorn 執行）
if __name__ == "__main__":
    app.run()
