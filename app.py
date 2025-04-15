from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
import logging
from deep_translator import GoogleTranslator
import openai

# 建立 Flask 應用
app = Flask(__name__)

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('app')

# LINE 機器人設定
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))

# OpenAI 設定（使用 GPT-4）
openai.api_key = os.environ.get("OPENAI_API_KEY")
OCR_API_KEY = os.environ.get("OCR_API_KEY")

@app.route("/")
def index():
    return "LINE GPT Bot is running."

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    logger.info(f"收到 LINE Webhook 請求")
    logger.info(f"Headers: {request.headers}")
    logger.info(f"Body: {body}")

    try:
        handler.handle(body, signature)
    except Exception as e:
        logger.error(f"處理 webhook 請求時發生錯誤: {e}")
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text
    logger.info(f"收到文字訊息: {user_text}")

    try:
        gpt_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一位智慧助理，請根據使用者訊息提供有幫助的說明。"},
                {"role": "user", "content": user_text}
            ]
        )
        reply_text = gpt_response['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"回覆文字訊息時錯誤: {e}")
        reply_text = "發生錯誤，請稍後再試。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    logger.info("📥 收到圖片訊息，開始處理圖片...")

    try:
        message_content = line_bot_api.get_message_content(event.message.id)
        image_path = f"/tmp/{event.message.id}.jpg"

        with open(image_path, 'wb') as f:
            for chunk in message_content.iter_content():
                f.write(chunk)

        logger.info(f"✅ 圖片下載成功: {image_path}")

        # OCR API 呼叫
        with open(image_path, 'rb') as image_file:
            response = requests.post(
                "https://api.ocr.space/parse/image",
                files={"file": image_file},
                data={"language": "eng", "isOverlayRequired": False},
                headers={"apikey": OCR_API_KEY}
            )

        result = response.json()
        parsed_text = result["ParsedResults"][0]["ParsedText"].strip()
        logger.info(f"📖 OCR 辨識結果: {parsed_text}")

        if not parsed_text:
            reply_text = "圖片中未辨識到任何文字。"
        else:
            # 自動語言偵測與翻譯
            try:
                detected_lang = GoogleTranslator(source='auto', target='zh-TW').detect(parsed_text)
                logger.info(f"🔍 偵測語言: {detected_lang}")

                if detected_lang.lower() not in ["zh", "zh-tw", "zh-cn", "zh-hant", "en"]:
                    translated_text = GoogleTranslator(source='auto', target='zh-TW').translate(parsed_text)
                    logger.info(f"🌐 翻譯後文字: {translated_text}")
                else:
                    translated_text = parsed_text

                # 交給 GPT-4 分析
                gpt_response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "你是一位智慧助理，請針對使用者提供的圖片文字進行有幫助的分析與說明。"},
                        {"role": "user", "content": translated_text}
                    ]
                )
                reply_text = gpt_response['choices'][0]['message']['content']

            except Exception as trans_error:
                logger.warning(f"翻譯時發生錯誤: {trans_error}")
                reply_text = f"辨識成功，但翻譯過程發生錯誤。原始文字：\n{parsed_text}"

    except Exception as e:
        logger.error(f"❌ 處理圖片時發生錯誤: {e}")
        reply_text = "處理圖片時發生錯誤，請稍後再試。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run()
