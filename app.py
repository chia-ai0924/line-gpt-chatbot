import os
import uuid
import threading
import time
from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from openai import OpenAI
import requests
from deep_translator import GoogleTranslator
from langdetect import detect
from io import BytesIO
import logging
import traceback

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ocr_api_key = os.environ.get("OCR_API_KEY")
SYSTEM_PROMPT = "你是一個智慧的 LINE 助理，請用繁體中文回答使用者的問題。"

def delete_file_after_delay(filepath, delay=180):
    def delete_later():
        time.sleep(delay)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"✅ 已自動刪除圖片：{filepath}")
        except Exception as e:
            print(f"❌ 刪除圖片失敗：{e}")
    threading.Thread(target=delete_later).start()

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

@app.route("/image/<image_id>")
def serve_image(image_id):
    filepath = f"/tmp/{image_id}.jpg"
    if os.path.exists(filepath):
        return send_file(filepath, mimetype="image/jpeg")
    else:
        return "圖片不存在或已刪除", 404
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    try:
        user_message = event.message.text
        print("收到文字訊息:", user_message)

        gpt_response = client.chat.completions.create(
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
        traceback.print_exc()
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="發生錯誤，請稍後再試。")
        )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        # 下載圖片並儲存到本機 /tmp
        image_content = line_bot_api.get_message_content(event.message.id)
        image_bytes = BytesIO()
        for chunk in image_content.iter_content():
            image_bytes.write(chunk)
        image_bytes.seek(0)

        image_id = str(uuid.uuid4())
        image_path = f"/tmp/{image_id}.jpg"
        with open(image_path, "wb") as f:
            f.write(image_bytes.getvalue())

        # 啟動刪除倒數（3分鐘）
        delete_file_after_delay(image_path, delay=180)
        image_url = f"{request.host_url}image/{image_id}"

        # 嘗試 OCR
        ocr_response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"filename": ("image.jpg", image_bytes, "image/jpeg")},
            data={"language": "eng", "apikey": ocr_api_key},
        )
        ocr_result = ocr_response.json()
        parsed_text = ocr_result["ParsedResults"][0]["ParsedText"]
        print("OCR 辨識結果:", parsed_text)

        # 根據是否有文字決定 GPT 提示
        if parsed_text.strip():
            try:
                lang = detect(parsed_text)
                print("語言偵測結果:", lang)
                if lang not in ["zh-cn", "zh-tw", "zh"]:
                    translated = GoogleTranslator(source='auto', target='zh-TW').translate(parsed_text)
                    print("翻譯後文字:", translated)
                else:
                    translated = parsed_text
            except:
                translated = parsed_text

            prompt = f"""以下是從圖片中辨識出的文字內容：

{translated}

請你根據這些資訊，用繁體中文說明這張圖片的可能內容、用途、背景，並提供一些有幫助的整理與描述。"""
            gpt_messages = [
                {"role": "system", "content": "你是一位圖片分析專家，請用繁體中文幫助使用者理解圖片中的內容與含意。"},
                {"role": "user", "content": prompt}
            ]
        else:
            gpt_messages = [
                {"role": "system", "content": "你是一位圖片分析專家，請用繁體中文幫助使用者理解圖片中的內容與含意。"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "以下是使用者提供的一張圖片，請用繁體中文智慧推測圖片內容、用途、背景，並提供一些有幫助的整理與說明。"},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ]

        # 呼叫 GPT Vision 模型
        gpt_response = client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=gpt_messages,
            max_tokens=1024
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
