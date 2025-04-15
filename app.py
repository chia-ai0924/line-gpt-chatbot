from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
import openai
from deep_translator import GoogleTranslator
from langdetect import detect
from io import BytesIO
from PIL import Image

app = Flask(__name__)

# 初始化設定
line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")

# OCR API 設定（以 OCR.Space 為例）
OCR_API_URL = "https://api.ocr.space/parse/image"
OCR_API_KEY = os.environ.get("OCR_API_KEY")

# 路由處理
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print("Webhook 處理錯誤:", e)
        abort(400)

    return "OK"

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_msg = event.message.text
    print("收到文字訊息:", user_msg)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一個回覆繁體中文的 LINE 聊天助手，請用自然、人性化、友善的語氣回覆使用者。"},
                {"role": "user", "content": user_msg}
            ]
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        print("回覆文字訊息時錯誤:", e)
        reply = "發生錯誤，請稍後再試。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

# 處理圖片訊息
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    print("收到圖片訊息，開始處理圖片...")

    try:
        # 下載圖片
        image_content = line_bot_api.get_message_content(event.message.id)
        image_data = BytesIO()
        for chunk in image_content.iter_content():
            image_data.write(chunk)
        image_data.seek(0)

        # 傳送到 OCR.Space 進行辨識
        print("🔍 傳送圖片到 OCR.Space...")
        ocr_response = requests.post(
            OCR_API_URL,
            files={"file": image_data},
            data={"apikey": OCR_API_KEY, "language": "eng"},
        )

        result = ocr_response.json()
        parsed_text = result["ParsedResults"][0]["ParsedText"]
        print("📖 OCR 辨識結果:", parsed_text)

        # 偵測語言
        detected_lang = detect(parsed_text)
        print("🌐 偵測語言:", detected_lang)

        # 翻譯成繁體中文（如果不是中文）
        if detected_lang not in ["zh-cn", "zh-tw"]:
            try:
                translated_text = GoogleTranslator(source="auto", target="zh-tw").translate(parsed_text)
            except Exception as e:
                print("⚠️ 翻譯時發生錯誤:", e)
                translated_text = None
        else:
            translated_text = parsed_text

        # 準備給 GPT 的分析指令
        gpt_prompt = f"""這是一段從圖片辨識出來的文字內容：
---
{translated_text}
---
請你以智慧方式判斷這是什麼圖片，並用繁體中文整理成一段有幫助的說明，例如：是菜單、公告、文件等。請用自然、友善的語氣回覆使用者，避免直接複製原文。"""

        try:
            gpt_response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "你是一個會分析圖片文字並用繁體中文智慧回應的 LINE 機器人。"},
                    {"role": "user", "content": gpt_prompt}
                ]
            )
            reply = gpt_response.choices[0].message.content.strip()
        except Exception as e:
            print("❌ GPT 分析圖片錯誤:", e)
            reply = f"辨識成功，但 GPT 回覆時發生錯誤。原始文字如下：\n{translated_text}"

    except Exception as e:
        print("❌ 圖片處理錯誤:", e)
        reply = "處理圖片時發生錯誤，請稍後再試。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()
