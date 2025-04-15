from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
from deep_translator import GoogleTranslator
from langdetect import detect
from openai import OpenAI
import logging
from io import BytesIO

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
ocr_api_key = os.getenv("OCR_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_message = event.message.text
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一個智慧 LINE 助理，請使用繁體中文回覆所有訊息。"},
                {"role": "user", "content": user_message}
            ]
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"文字回覆錯誤: {e}")
        reply = "發生錯誤，請稍後再試。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        image_content = line_bot_api.get_message_content(event.message.id)
        image_data = BytesIO()
        for chunk in image_content.iter_content():
            image_data.write(chunk)
        image_data.seek(0)

        ocr_response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"file": image_data},
            data={"apikey": ocr_api_key, "language": "eng"}
        )
        result = ocr_response.json()
        parsed_text = result["ParsedResults"][0]["ParsedText"].strip()

        try:
            lang = detect(parsed_text)
        except:
            lang = "unknown"

        if lang not in ["zh-cn", "zh-tw", "zh"]:
            try:
                translated = GoogleTranslator(source="auto", target="zh-TW").translate(parsed_text)
            except:
                translated = parsed_text
        else:
            translated = parsed_text

        prompt = f"""以下是使用者提供圖片中的內容（已辨識與翻譯）：
{translated}
請你用繁體中文描述這是什麼圖片、它的用途、重點內容或推測的情境，語氣自然、友善、有幫助。"""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一個圖片文字分析專家，請使用繁體中文智慧地說明圖片內容。"},
                {"role": "user", "content": prompt}
            ]
        )
        reply = response.choices[0].message.content.strip()

    except Exception as e:
        logging.error(f"處理圖片時錯誤: {e}")
        reply = "處理圖片時發生錯誤，請稍後再試。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()
