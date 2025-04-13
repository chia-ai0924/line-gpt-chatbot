from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage

import os
import openai
import requests
from PIL import Image
import pytesseract
from io import BytesIO
from deep_translator import GoogleTranslator

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_message = event.message.text

    reply = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": user_message}
        ]
    )

    reply_text = reply.choices[0].message.content.strip()
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    # 取得圖片內容
    image_content = line_bot_api.get_message_content(event.message.id)
    image_bytes = BytesIO(image_content.content)

    # 開啟圖片並 OCR 辨識
    image = Image.open(image_bytes)
    ocr_text = pytesseract.image_to_string(image)

    # 偵測是否非中文（簡易判斷）
    if not any('\u4e00' <= ch <= '\u9fff' for ch in ocr_text):
        translated_text = GoogleTranslator(source='auto', target='zh-tw').translate(ocr_text)
    else:
        translated_text = ocr_text

    # 生成描述性回應
    prompt = f"這張圖片中的文字是：{translated_text}\n請幫我用一段自然的中文說明這張圖片的內容。"
    reply = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    reply_text = reply.choices[0].message.content.strip()
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
