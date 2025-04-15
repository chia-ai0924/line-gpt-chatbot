from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
import openai
import logging
from deep_translator import GoogleTranslator
from langdetect import detect

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
openai.api_key = os.getenv("OPENAI_API_KEY")
ocr_api_key = os.getenv("OCR_API_KEY")

# Webhook endpoint
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    logging.info(f"收到請求: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logging.error("❌ 簽名驗證錯誤")
        abort(400)
    return 'OK'

# 文字訊息處理
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_message = event.message.text
    logging.info(f"收到文字訊息: {user_message}")

    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一個親切且專業的中文助理，所有回覆請使用繁體中文。"},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7
        )
        reply_text = response.choices[0].message.content.strip()
        logging.info(f"GPT 回覆文字: {reply_text}")
    except Exception as e:
        logging.error(f"回覆文字訊息時錯誤: {e}")
        reply_text = "發生錯誤，請稍後再試。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

# 圖片訊息處理
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        logging.info("📩 收到圖片訊息，開始處理圖片...")

        message_content = line_bot_api.get_message_content(event.message.id)
        image_path = f"/tmp/{event.message.id}.jpg"
        with open(image_path, 'wb') as f:
            for chunk in message_content.iter_content():
                f.write(chunk)
        logging.info(f"✅ 圖片下載成功: {image_path}")

        with open(image_path, 'rb') as image_file:
            ocr_response = requests.post(
                'https://api.ocr.space/parse/image',
                files={'filename': image_file},
                data={'apikey': ocr_api_key, 'language': 'eng'}
            )
        result = ocr_response.json()
        parsed_text = result['ParsedResults'][0]['ParsedText']
        logging.info(f"🧠 OCR 辨識結果: {parsed_text}")

        try:
            lang = detect(parsed_text)
        except Exception as e:
            logging.warning(f"語言偵測失敗: {e}")
            lang = "unknown"

        if lang not in ["zh-cn", "zh-tw", "zh"]:
            try:
                translated = GoogleTranslator(source='auto', target='zh-TW').translate(parsed_text)
                logging.info(f"🌐 翻譯為繁體中文: {translated}")
                user_prompt = f"以下是圖片中的英文內容，請幫我用繁體中文說明內容是什麼，以及它可能的用途或情境：\n{translated}"
            except Exception as e:
                logging.warning(f"翻譯時發生錯誤: {e}")
                user_prompt = f"圖片內容為：\n{parsed_text}\n（原文翻譯失敗）"
        else:
            user_prompt = f"圖片內容為：\n{parsed_text}\n請你用繁體中文幫我說明這張圖片可能的用途或情境。"

        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一個智慧助理，請使用繁體中文提供圖片文字的說明與分析。"},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7
        )
        reply_text = response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"GPT 圖片分析時發生錯誤: {e}")
        reply_text = "圖片分析時發生錯誤，請稍後再試。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run()
