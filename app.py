from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
from deep_translator import GoogleTranslator
import openai

app = Flask(__name__)

# 初始化
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")
ocr_api_key = os.environ.get("OCR_API_KEY")

@app.route("/", methods=['GET'])
def index():
    return {"status": "Chatbot is running"}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'  # <-- 非常重要，Webhook 驗證需要這個

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    # 取得圖片
    image_id = event.message.id
    content = line_bot_api.get_message_content(image_id)
    image_path = f"/tmp/{image_id}.jpg"
    with open(image_path, "wb") as f:
        for chunk in content.iter_content():
            f.write(chunk)

    # 傳送至 OCR API
    with open(image_path, "rb") as image_file:
        res = requests.post(
            "https://api.ocr.space/parse/image",
            files={"filename": image_file},
            data={"apikey": ocr_api_key, "language": "eng"}
        )
    result = res.json()
    text = result.get("ParsedResults", [{}])[0].get("ParsedText", "").strip()

    # 翻譯成中文（如果不是中文）
    try:
        if not any(u'\u4e00' <= ch <= u'\u9fff' for ch in text):
            text = GoogleTranslator(source='auto', target='zh-tw').translate(text)
    except Exception as e:
        text += f"\n\n⚠️ 翻譯失敗：{str(e)}"

    # 請 GPT 分析
    try:
        prompt = f"這段文字是從圖片辨識出來的內容：\n{text}\n\n請幫我分析並用繁體中文說明這段內容可能的意義、用途或需要注意的地方："
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        answer = f"⚠️ 無法使用 GPT 回應：{str(e)}"

    # 回覆用戶
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=answer)
    )

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="請傳送圖片給我，我可以幫你辨識並解釋裡面的文字。")
    )

if __name__ == "__main__":
    app.run()
