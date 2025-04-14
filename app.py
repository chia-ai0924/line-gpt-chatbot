import os
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from openai import OpenAI
from deep_translator import GoogleTranslator

app = Flask(__name__)

# 環境變數
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai_api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")

# 初始化 OpenAI
openai = OpenAI(api_key=openai_api_key)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("LINE 處理失敗：", e)
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_message = event.message.text

    reply = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{ "role": "user", "content": user_message }]
    )

    reply_text = reply.choices[0].message.content.strip()

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    # 下載圖片內容
    message_content = line_bot_api.get_message_content(event.message.id)
    image_data = b''.join(chunk for chunk in message_content.iter_content())

    # 發送到 OCR.Space API 辨識文字
    ocr_response = requests.post(
        "https://api.ocr.space/parse/image",
        files={"filename": ("image.jpg", image_data)},
        data={"apikey": ocr_api_key, "language": "eng"},
    )

    result = ocr_response.json()
    try:
        parsed_text = result["ParsedResults"][0]["ParsedText"]
    except:
        parsed_text = ""

    # 偵測是否為中文，若不是則翻譯
    def is_chinese(text):
        return any('\u4e00' <= ch <= '\u9fff' for ch in text)

    if not is_chinese(parsed_text):
        parsed_text = GoogleTranslator(source='auto', target='zh-tw').translate(parsed_text)

    # 請 ChatGPT 幫忙描述圖片內容
    prompt = f"請根據以下圖片中的文字，幫我描述這張圖片的內容給一般人聽：\n\n{parsed_text}"
    gpt_reply = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{ "role": "user", "content": prompt }]
    )
    reply_text = gpt_reply.choices[0].message.content.strip()

    # 回傳結果
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
