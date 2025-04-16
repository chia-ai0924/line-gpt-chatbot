
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
import openai
from deep_translator import GoogleTranslator
from PIL import Image
from io import BytesIO
import uuid
import threading
import time
from urllib.parse import urlencode

# 初始化
app = Flask(__name__)
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")
image_auth_token = os.environ.get("IMAGE_AUTH_TOKEN", "default_token")

# 建立 static 資料夾
STATIC_IMAGE_DIR = "static/images"
os.makedirs(STATIC_IMAGE_DIR, exist_ok=True)

# 圖片刪除排程
def schedule_delete(file_path, delay=180):
    def delete_file():
        time.sleep(delay)
        try:
            os.remove(file_path)
        except Exception:
            pass
    threading.Thread(target=delete_file).start()

# 提供 GPT 可存取圖片網址，但需附加 auth token
@app.route("/image/<filename>")
def serve_image(filename):
    token = request.args.get("auth")
    if token != image_auth_token:
        abort(403)
    return send_from_directory(STATIC_IMAGE_DIR, filename)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("ERROR:", e)
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": user_text}]
    )
    reply = response.choices[0].message.content.strip()
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        message_content = line_bot_api.get_message_content(event.message.id)
        image_data = BytesIO(message_content.content)
        image = Image.open(image_data)

        filename = f"{uuid.uuid4()}.jpg"
        image_path = os.path.join(STATIC_IMAGE_DIR, filename)
        image.save(image_path)
        schedule_delete(image_path)

        # 呼叫 OCR.Space API
        ocr_response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"file": open(image_path, "rb")},
            data={"language": "chs", "isOverlayRequired": False},
            headers={"apikey": ocr_api_key}
        )
        ocr_result = ocr_response.json()
        parsed_text = ocr_result.get("ParsedResults", [{}])[0].get("ParsedText", "").strip()

        # 準備 GPT 分析內容
        image_url = f"{request.url_root}image/{filename}?{urlencode({'auth': image_auth_token})}"
        prompt =prompt = f"這是使用者提供的圖片內容，請用繁體中文分析其含意，若圖片中有文字為主，請加以整理翻譯，若是圖像為主，請說明圖像內容："

{parsed_text}
圖片網址：{image_url}"

        gpt_response = openai.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": image_url}}]}],
            max_tokens=1000
        )
        final_reply = gpt_response.choices[0].message.content.strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=final_reply))
    except Exception as e:
        print("圖片處理錯誤:", e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="圖片分析失敗，請稍後再試～"))

# 啟動應用
if __name__ == "__main__":
    app.run()
