import os
import logging
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from deep_translator import GoogleTranslator
import openai

# 設定 log 顯示格式與等級
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 建立 Flask 應用程式
app = Flask(__name__)

# 從環境變數讀取密鑰
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")

# 預設首頁測試用
@app.route("/")
def home():
    return {"status": "Chatbot is running"}

# Webhook 路由處理
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    logger.info("收到請求：%s", body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("簽名驗證失敗")
        abort(400)

    return 'OK'

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    text = event.message.text
    logger.info("收到文字訊息：%s", text)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是智慧 LINE 助理，擅長分析文字、翻譯與給予說明。"},
                {"role": "user", "content": text}
            ]
        )
        reply = response.choices[0].message.content
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    except Exception as e:
        logger.error("回覆文字訊息時錯誤：%s", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="發生錯誤，請稍後再試。"))

# 處理圖片訊息
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        logger.info("收到圖片訊息")

        # 下載圖片
        message_content = line_bot_api.get_message_content(event.message.id)
        image_path = f"/tmp/{event.message.id}.jpg"
        with open(image_path, 'wb') as f:
            for chunk in message_content.iter_content():
                f.write(chunk)
        logger.info("圖片下載完成：%s", image_path)

        # 傳給 OCR.Space API 進行文字辨識
        with open(image_path, 'rb') as img:
            res = requests.post(
                "https://api.ocr.space/parse/image",
                files={"file": img},
                data={"language": "eng", "isOverlayRequired": False},
                headers={"apikey": ocr_api_key}
            )
        result = res.json()
        logger.debug("OCR API 回應：%s", result)

        parsed_text = result['ParsedResults'][0]['ParsedText']
        logger.info("OCR 辨識文字：%s", parsed_text.strip())

        # 自動翻譯（如果不是中文）
        if not any('\u4e00' <= char <= '\u9fff' for char in parsed_text):
            translated = GoogleTranslator(source='auto', target='zh-tw').translate(parsed_text)
            logger.info("翻譯後內容：%s", translated)
        else:
            translated = parsed_text

        # 用 GPT 回覆解釋
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是圖片助理，會根據辨識出的文字給出清楚的說明與分析。"},
                {"role": "user", "content": translated}
            ]
        )
        reply_text = response.choices[0].message.content
        logger.info("GPT 回覆內容：%s", reply_text)

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    except Exception as e:
        logger.error("處理圖片時發生錯誤：%s", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="處理圖片時發生錯誤，請稍後再試。"))

