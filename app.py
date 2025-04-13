from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage

import os
import requests
from io import BytesIO
from PIL import Image
import openai

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

# ✅ 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
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

# ✅ 處理圖片訊息（OCR + 翻譯 + 回覆描述）
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    # 下載圖片內容
    message_content = line_bot_api.get_message_content(event.message.id)
    image_data = BytesIO(message_content.content)

    # 將圖片上傳到 OpenAI Vision API 並取得回應
    base64_image = f"data:image/jpeg;base64,{image_data.getvalue().hex()}"
    response = openai.ChatCompletion.create(
        model="gpt-4-vision-preview",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "這是一張使用者上傳的圖片，請你看圖辨識裡面的文字與內容，若非中文請翻譯，然後用中文整理並描述這張圖片裡的資訊。"},
                    {"type": "image_url", "image_url": {"url": base64_image}},
                ],
            }
        ],
        max_tokens=800
    )

    result = response.choices[0].message.content.strip()

    # 回覆使用者
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=result)
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

