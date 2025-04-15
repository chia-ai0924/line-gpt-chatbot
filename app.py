from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from deep_translator import GoogleTranslator
from openai import OpenAI
import os
import requests
import logging

app = Flask(__name__)

# Logging 設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# 初始化
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ocr_api_key = os.environ.get("OCR_API_KEY")

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    logger.info(f"收到 LINE Webhook 請求")
    logger.info(f"Headers: {request.headers}")
    logger.info(f"Body: {body}")

    try:
        handler.handle(body, signature)
    except Exception as e:
        logger.exception("處理 webhook 時發生錯誤")
        return 'Error', 400

    return 'OK', 200

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    try:
        user_msg = event.message.text
        logger.info(f"收到文字訊息: {user_msg}")

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": user_msg}]
        )
        reply = response.choices[0].message.content.strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        logger.exception("回覆文字訊息時錯誤")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="發生錯誤，請稍後再試。"))

# 處理圖片訊息
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        logger.info("📥 收到圖片訊息，開始處理圖片...")

        # 下載圖片
        message_content = line_bot_api.get_message_content(event.message.id)
        image_path = f"/tmp/{event.message.id}.jpg"
        with open(image_path, 'wb') as f:
            for chunk in message_content.iter_content():
                f.write(chunk)
        logger.info(f"✅ 圖片下載成功: {image_path}")

        # OCR 辨識圖片文字
        ocr_result = requests.post(
            "https://api.ocr.space/parse/image",
            data={"apikey": ocr_api_key, "language": "eng"},
            files={"filename": open(image_path, "rb")}
        ).json()
        parsed_text = ocr_result['ParsedResults'][0]['ParsedText']
        logger.info(f"🧠 OCR 辨識結果: {parsed_text}")

        # 自動偵測語言 → 若非中文或英文，則翻譯成中文
        try:
            detected_lang = GoogleTranslator().detect(parsed_text)
            logger.info(f"🔍 偵測語言: {detected_lang}")
        except Exception as e:
            detected_lang = "unknown"
            logger.warning(f"翻譯時發生錯誤: {e}")

        # 若非中文或英文，進行翻譯
        if detected_lang not in ["zh-CN", "zh-TW", "en"]:
            try:
                translated_text = GoogleTranslator(source='auto', target='zh-TW').translate(parsed_text)
                logger.info(f"🌐 翻譯成中文: {translated_text}")
            except Exception as e:
                translated_text = None
                logger.warning(f"⚠️ 翻譯失敗: {e}")
        else:
            translated_text = parsed_text

        # 使用 GPT 分析並生成說明
        try:
            content_to_ask = translated_text if translated_text else parsed_text
            gpt_response = client.chat.completions.create(
                model="gpt-4",
                messages=[{
                    "role": "system",
                    "content": "你是一個智慧助理，請根據圖片辨識文字給予有幫助的解說。"
                }, {
                    "role": "user",
                    "content": f"以下是圖片中擷取的文字內容：\n{content_to_ask}"
                }]
            )
            reply = gpt_response.choices[0].message.content.strip()
        except Exception as e:
            logger.exception("GPT 回應失敗")
            reply = f"辨識成功，但翻譯或 GPT 回覆過程發生錯誤。\n原始文字：\n{parsed_text}"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    except Exception as e:
        logger.exception("處理圖片時發生錯誤")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="處理圖片時發生錯誤，請稍後再試。"))

if __name__ == "__main__":
    app.run()
