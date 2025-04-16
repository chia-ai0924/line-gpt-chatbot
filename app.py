import os
import uuid
import requests
import shutil
import threading
from flask import Flask, request, send_from_directory, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from PIL import Image
from openai import OpenAI
import time

# 初始化 Flask 應用與 LINE、OpenAI 客戶端
app = Flask(__name__, static_url_path="/static", static_folder="static")

line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_SECRET"))
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
OCR_API_KEY = os.environ.get("OCR_API_KEY")
STATIC_IMAGE_DIR = "./static/images"

# 確保圖片資料夾存在
os.makedirs(STATIC_IMAGE_DIR, exist_ok=True)

# 自動刪除圖片
def delete_file_later(path, delay=180):
    def delete():
        time.sleep(delay)
        try:
            os.remove(path)
        except:
            pass
    threading.Thread(target=delete).start()

# 圖片路由，加入驗證 token
@app.route("/image/<filename>")
def serve_image(filename):
    token = request.args.get("auth")
    if not token or token != filename.split(".")[0][-12:]:
        abort(403)
    return send_from_directory(STATIC_IMAGE_DIR, filename)

# 主 webhook 處理
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    try:
        # 儲存圖片
        message_id = event.message.id
        image_content = line_bot_api.get_message_content(message_id)
        filename = f"{uuid.uuid4()}.jpg"
        filepath = os.path.join(STATIC_IMAGE_DIR, filename)
        with open(filepath, "wb") as f:
            shutil.copyfileobj(image_content.content, f)

        delete_file_later(filepath)  # 自動刪除

        # 上傳至 OCR.Space 辨識
        with open(filepath, "rb") as image_file:
            ocr_response = requests.post(
                "https://api.ocr.space/parse/image",
                files={"file": image_file},
                data={"language": "cht", "isOverlayRequired": False},
                headers={"apikey": OCR_API_KEY}
            )
        ocr_result = ocr_response.json()
        parsed_text = ocr_result["ParsedResults"][0]["ParsedText"].strip() if "ParsedResults" in ocr_result else ""

        # 建立圖片網址給 GPT 分析
        token = filename.split(".")[0][-12:]
        image_url = f"https://{request.host}/image/{filename}?auth={token}"

        # 整合 GPT Vision
        prompt = f"這是使用者提供的圖片內容，請用繁體中文分析其含意，若圖片中有文字為主，請加以整理翻譯，若是圖像為主，請說明圖像內容：

可參考圖片網址：{image_url}"
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": image_url}}]}]
        gpt_response = client.chat.completions.create(model="gpt-4-vision-preview", messages=messages, max_tokens=1000)
        reply_text = gpt_response.choices[0].message.content.strip()

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="圖片處理錯誤，請稍後再試。"))
        print("ERROR:root:圖片處理錯誤\n", e)

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    try:
        user_message = event.message.text
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": user_message}],
            max_tokens=1000
        )
        reply_text = response.choices[0].message.content.strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="處理訊息時發生錯誤"))
        print("ERROR:root:訊息處理錯誤\n", e)

if __name__ == "__main__":
    app.run()
