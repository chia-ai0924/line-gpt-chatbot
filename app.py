from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
import tempfile
from deep_translator import GoogleTranslator
from langdetect import detect
from openai import OpenAI
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
ocr_api_key = os.environ.get("OCR_API_KEY")
openai_api_key = os.environ.get("OPENAI_API_KEY")
openai = OpenAI(api_key=openai_api_key)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("收到回傳資料：%s", body)
    try:
        handler.handle(body, signature)
    except Exception as e:
        app.logger.error("處理 webhook 時發生錯誤：%s", str(e))
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    try:
        user_message = event.message.text
        app.logger.info("收到文字訊息：%s", user_message)
        
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一個智慧助理，請用繁體中文回答所有問題。"},
                {"role": "user", "content": user_message}
            ]
        )
        reply = response.choices[0].message.content.strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        app.logger.error("回覆文字訊息時錯誤：%s", str(e))
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="發生錯誤，請稍後再試。"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        app.logger.info("收到圖片訊息，開始處理圖片...")
        image_content = line_bot_api.get_message_content(event.message.id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
            for chunk in image_content.iter_content():
                tf.write(chunk)
            temp_image_path = tf.name

        app.logger.info("圖片下載成功：%s", temp_image_path)

        # OCR 辨識
        with open(temp_image_path, 'rb') as img_file:
            res = requests.post(
                'https://api.ocr.space/parse/image',
                files={'file': img_file},
                data={'apikey': ocr_api_key, 'language': 'eng'}
            )
        ocr_result = res.json()
        text = ocr_result['ParsedResults'][0]['ParsedText']
        app.logger.info("OCR 辨識結果：%s", text)

        # 偵測語言
        try:
            lang = detect(text)
        except:
            lang = 'unknown'

        app.logger.info("辨識語言為：%s", lang)

        if lang.startswith('zh'):
            final_text = text
        else:
            try:
                translated = GoogleTranslator(source='auto', target='zh-TW').translate(text)
                final_text = f"圖片內容為（已翻譯）：\n{translated}"
            except Exception as e:
                app.logger.warning("翻譯時發生錯誤：%s", str(e))
                final_text = f"辨識成功，但翻譯過程發生錯誤。原始文字：\n{text}"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=final_text))

    except Exception as e:
        app.logger.error("GPT 圖片分析時發生錯誤：%s", str(e))
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="處理圖片時發生錯誤，請稍後再試。"))

if __name__ == "__main__":
    app.run()
