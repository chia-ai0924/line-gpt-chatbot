from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
import os
import requests
from PIL import Image
from io import BytesIO
import openai
import pytesseract
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
    except:
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
    # 下載圖片
    message_content = line_bot_api.get_message_content(event.message.id)
    image_data = BytesIO(message_content.content)

    # 讀取圖片並進行 OCR
    image = Image.open(image_data)
    extracted_text = pytesseract.image_to_string(image)

    # 判斷是否需要翻譯（若中文字元比例太少）
    chinese_chars = sum(1 for c in extracted_text if '\u4e00' <= c <= '\u9fff')
    if chinese_chars < len(extracted_text) * 0.3:
        translated_text = GoogleTranslator(source='auto', target='zh-tw').translate(extracted_text)
    else:
        translated_text = extracted_text

    # 丟給 GPT 做說明
    prompt = f"這是一張圖片，裡面的文字是：{translated_text}\n請幫我說明這張圖片的內容，並補充一些實用的背景知識或建議。"
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

