from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import openai
from openai import OpenAI
import os
import requests
from PIL import Image
from io import BytesIO
import pytesseract
from deep_translator import GoogleTranslator

app = Flask(__name__)

# LINE 與 OpenAI 初始化
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai_api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")

openai = OpenAI(api_key=openai_api_key)

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

    # 發送給 GPT 模型
    reply = openai.chat.completions.create(
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
    message_id = event.message.id
    message_content = line_bot_api.get_message_content(message_id)
    image = Image.open(BytesIO(message_content.content))

    # OCR 辨識圖片中文字
    ocr_text = pytesseract.image_to_string(image).strip()

    # 如果不是中文，則翻譯成中文
    try:
        if not any('\u4e00' <= char <= '\u9fff' for char in ocr_text):
            ocr_text = GoogleTranslator(source='auto', target='zh-TW').translate(ocr_text)
    except:
        ocr_text = "圖片內文字無法辨識或翻譯。"

    # 傳給 ChatGPT 生成回應
    reply = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "你是一個親切的圖片助理，會根據圖片內容的文字提供有幫助的說明。"},
            {"role": "user", "content": f"請根據這段圖片中的文字內容說明給我聽：{ocr_text}"}
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
