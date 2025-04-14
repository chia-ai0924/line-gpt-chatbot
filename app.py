from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
from deep_translator import GoogleTranslator
import openai

app = Flask(__name__)

# 讀取環境變數，並加上 log 確認
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
OCR_API_KEY = os.environ.get("OCR_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# 驗證環境變數
if not LINE_CHANNEL_ACCESS_TOKEN:
    print("[ERROR] LINE_ACCESS_TOKEN 環境變數沒有設好")
if not LINE_CHANNEL_SECRET:
    print("[ERROR] LINE_CHANNEL_SECRET 環境變數沒有設好")
if not OCR_API_KEY:
    print("[ERROR] OCR_API_KEY 環境變數沒有設好")
if not OPENAI_API_KEY:
    print("[ERROR] OPENAI_API_KEY 環境變數沒有設好")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

@app.route("/", methods=["GET"])
def home():
    return {"status": "Chatbot is running"}

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    print(f"[INFO] Received body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("[ERROR] Invalid signature")
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_text = event.message.text
    print(f"[INFO] Received text: {user_text}")

    # 使用 OpenAI 回答
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": user_text}],
        temperature=0.7,
    )

    reply_text = response['choices'][0]['message']['content'].strip()
    print(f"[INFO] GPT reply: {reply_text}")
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    print("[INFO] 處理圖片訊息")
    message_content = line_bot_api.get_message_content(event.message.id)

    with open("temp.jpg", "wb") as f:
        for chunk in message_content.iter_content():
            f.write(chunk)

    with open("temp.jpg", "rb") as f:
        response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"file": f},
            data={"apikey": OCR_API_KEY, "language": "eng"},
        )
    result = response.json()
    parsed_text = result.get("ParsedResults", [{}])[0].get("ParsedText", "").strip()
    print(f"[INFO] OCR 文字：{parsed_text}")

    if not parsed_text:
        reply = "圖片中未偵測到可辨識的文字"
    else:
        try:
            translated = GoogleTranslator(source="auto", target="zh-tw").translate(parsed_text)
            reply = f"圖片文字翻譯為：\n{translated}"
        except Exception as e:
            print(f"[ERROR] 翻譯失敗：{e}")
            reply = f"偵測到的文字：\n{parsed_text}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run()
