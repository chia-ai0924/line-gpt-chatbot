from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import openai
import os
import requests
from PIL import Image
import pytesseract
from deep_translator import GoogleTranslator
from io import BytesIO

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")

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
            {'role': 'user', 'content': user_message}
        ]
    )

    reply_text = reply.choices[0].message.content.strip()
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    message_content = line_bot_api.get_message_content(event.message.id)
    image_data = BytesIO(message_content.content)
    image = Image.open(image_data)

    # 使用 pytesseract 擷取圖片中文字
    ocr_text = pytesseract.image_to_string(image).strip()

    # 如果文字為空，使用 OCR.Space 當備用
    if not ocr_text:
        ocr_text = ocr_space_ocr(image_data)

    # 偵測是否為中文（很粗略，只抓是否包含中文字）
    contains_chinese = any('\u4e00' <= ch <= '\u9fff' for ch in ocr_text)

    # 翻譯非中文文字為中文
    if not contains_chinese and ocr_text:
        translated = GoogleTranslator(source='auto', target='zh-TW').translate(ocr_text)
    else:
        translated = ocr_text if ocr_text else "抱歉，這張圖片無法辨識出任何文字。"

    # 發送 ChatGPT 描述回應
    gpt_prompt = f"這是從圖片中辨識出的文字內容：\n「{translated}」\n請你根據這段內容，簡要描述這張圖片可能是在說什麼。"
    reply = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{'role': 'user', 'content': gpt_prompt}]
    )

    reply_text = reply.choices[0].message.content.strip()
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

def ocr_space_ocr(image_data):
    """使用 OCR.Space 備援 OCR"""
    image_data.seek(0)
    response = requests.post(
        'https://api.ocr.space/parse/image',
        files={'filename': image_data},
        data={'language': 'eng', 'apikey': ocr_api_key}
    )
    result = response.json()
    if result['IsErroredOnProcessing'] or not result['ParsedResults']:
        return ""
    return result['ParsedResults'][0]['ParsedText'].strip()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
