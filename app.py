from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage

import os
import logging
import requests
from deep_translator import GoogleTranslator
import openai

# 啟用 logging 記錄
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# 環境變數
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")

@app.route("/", methods=['GET'])
def index():
    logging.info("✅ 服務啟動成功")
    return {"status": "Chatbot is running"}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    logging.info("📨 收到 LINE 請求")
    logging.info(f"Headers: {dict(request.headers)}")
    logging.info(f"Body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logging.error("❌ 簽名驗證失敗")
        abort(400)
    except Exception as e:
        logging.exception(f"❌ webhook callback 發生例外錯誤：{str(e)}")
        abort(500)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_msg = event.message.text
    logging.info(f"✉️ 收到文字訊息：{user_msg}")

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "你是一個智慧 LINE 機器人，請提供有幫助且自然的回答。"},
                {"role": "user", "content": user_msg}
            ]
        )
        reply = response['choices'][0]['message']['content']
        logging.info(f"🧠 GPT 回覆：{reply}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        logging.exception("❌ GPT 回應失敗")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="很抱歉，AI 回覆時發生錯誤。"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    logging.info("🖼️ 收到圖片訊息，開始處理圖片文字辨識")

    try:
        # 下載圖片內容
        message_content = line_bot_api.get_message_content(event.message.id)
        image_data = message_content.content
        logging.info("✅ 圖片下載完成")

        # 上傳至 OCR.Space
        response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"filename": image_data},
            data={"apikey": ocr_api_key, "language": "eng"},
        )

        result = response.json()
        parsed_text = result['ParsedResults'][0]['ParsedText']
        logging.info(f"🔍 OCR 辨識結果：{parsed_text}")

        # 自動翻譯成中文（若非中文）
        if not any(u'\u4e00' <= c <= u'\u9fff' for c in parsed_text):
            translated_text = GoogleTranslator(source='auto', target='zh-tw').translate(parsed_text)
            logging.info(f"🌐 翻譯為中文：{translated_text}")
        else:
            translated_text = parsed_text
            logging.info("🌐 內容為中文，無需翻譯")

        # GPT 分析與說明
        gpt_prompt = f"以下是圖片內的文字內容：{translated_text}。請針對這段內容提供一段智慧、有幫助的說明："
        gpt_reply = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "你是一個圖片分析助手，會針對 OCR 結果提供有幫助的中文說明。"},
                {"role": "user", "content": gpt_prompt}
            ]
        )['choices'][0]['message']['content']

        logging.info(f"🧠 GPT 圖片回應：{gpt_reply}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=gpt_reply))

    except Exception as e:
        logging.exception("❌ 圖片處理過程出錯")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="很抱歉，圖片處理時發生錯誤。"))

if __name__ == "__main__":
    app.run()
