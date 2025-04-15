from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
import openai
from deep_translator import GoogleTranslator
from langdetect import detect
from PIL import Image
from io import BytesIO
import base64
import logging

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")

# 繁體中文系統提示（未來如要調整角色可修改）
SYSTEM_PROMPT = "你是一個智慧的 LINE 助理，請用繁體中文回答使用者的問題。"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"處理訊息時發生錯誤: {e}")
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    try:
        user_message = event.message.text
        print("收到文字訊息:", user_message)

        gpt_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        )

        reply_text = gpt_response.choices[0].message.content.strip()
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except Exception as e:
        print("回覆文字訊息時發生錯誤:", e)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="發生錯誤，請稍後再試。")
        )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        # 下載圖片
        image_content = line_bot_api.get_message_content(event.message.id)
        image_bytes = BytesIO()
        for chunk in image_content.iter_content():
            image_bytes.write(chunk)
        image_data = image_bytes.getvalue()
        print("圖片下載成功")

        # 上傳至 OCR.Space
        ocr_response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"filename": image_data},
            data={"language": "eng", "apikey": ocr_api_key},
        )

        ocr_result = ocr_response.json()
        parsed_text = ocr_result["ParsedResults"][0]["ParsedText"]
        print("OCR 辨識結果:", parsed_text)

        if not parsed_text.strip():
            raise ValueError("圖片中未偵測到文字")

        # 偵測語言與翻譯（若非中文）
        try:
            lang = detect(parsed_text)
            print("語言偵測結果:", lang)
            if lang not in ["zh-cn", "zh-tw", "zh"]:
                translated = GoogleTranslator(source='auto', target='zh-TW').translate(parsed_text)
                print("翻譯後文字:", translated)
            else:
                translated = parsed_text
        except Exception as e:
            print("翻譯時發生錯誤:", e)
            translated = parsed_text  # fallback 使用原文

        # 使用 GPT 分析圖片內容
        prompt = f"""以下是從圖片中辨識出的文字內容：

{translated}

請你根據這些資訊，用繁體中文說明這張圖片的可能內容、用途、背景，並提供一些有幫助的整理與描述。"""

        gpt_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一位圖片分析專家，請用繁體中文聰明地幫助使用者理解圖片中的文字內容與含意。"},
                {"role": "user", "content": prompt}
            ]
        )

        reply_text = gpt_response.choices[0].message.content.strip()
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except Exception as e:
        logging.exception("圖片處理錯誤")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="處理圖片時發生錯誤，請稍後再試。")
        )

if __name__ == "__main__":
    app.run()

