from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import os
import requests
from deep_translator import GoogleTranslator
from langdetect import detect
from PIL import Image
from io import BytesIO
import openai
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

line_bot_api = LineBotApi(os.getenv("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_SECRET"))
openai.api_key = os.getenv("OPENAI_API_KEY")
OCR_API_KEY = os.getenv("OCR_API_KEY")

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# 文字訊息處理
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text
    logging.info("收到文字訊息: %s", user_text)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是個智慧的繁體中文助理，所有回覆都使用繁體中文。"},
                {"role": "user", "content": user_text}
            ]
        )
        reply = response["choices"][0]["message"]["content"].strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        logging.error("回覆文字訊息時錯誤: %s", str(e))
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="發生錯誤，請稍後再試。"))

# 圖片訊息處理
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    logging.info("📩 收到圖片訊息，開始處理圖片...")

    try:
        message_content = line_bot_api.get_message_content(event.message.id)
        image_data = BytesIO(message_content.content)

        # 轉成可上傳格式
        files = {"file": ("image.jpg", image_data, "image/jpeg")}
        payload = {
            "apikey": OCR_API_KEY,
            "language": "eng",
            "isOverlayRequired": False,
        }

        res = requests.post("https://api.ocr.space/parse/image", files=files, data=payload)
        result = res.json()
        logging.info("📋 OCR 結果：%s", result)

        if result.get("IsErroredOnProcessing") or "ParsedResults" not in result:
            raise ValueError("OCR API 處理錯誤")

        text = result["ParsedResults"][0].get("ParsedText", "").strip()

        if not text:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="圖片中沒有辨識到文字內容。"))
            return

        try:
            lang = detect(text)
        except Exception:
            lang = "unknown"

        # 翻譯成繁體中文
        if lang != "zh-tw" and lang != "zh-cn":
            try:
                translated = GoogleTranslator(source="auto", target="zh-tw").translate(text)
            except Exception as e:
                logging.warning("翻譯時發生錯誤: %s", str(e))
                translated = None
        else:
            translated = text

        # 使用 GPT 生成說明
        gpt_prompt = f"""以下是從圖片中辨識出來的文字內容：
{text}

請根據內容判斷這可能是什麼圖片，並用繁體中文給出一段人性化、有幫助的說明。"""
        if translated and translated != text:
            gpt_prompt += f"\n\n翻譯內容如下：\n{translated}"

        gpt_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是個圖片辨識小幫手，請根據 OCR 文字內容，生成繁體中文說明，幫助使用者理解圖片內容。"},
                {"role": "user", "content": gpt_prompt}
            ]
        )
        final_reply = gpt_response["choices"][0]["message"]["content"].strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=final_reply))

    except Exception as e:
        logging.error("❌ 處理圖片時發生錯誤: %s", str(e))
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="處理圖片時發生錯誤，請稍後再試。"))

if __name__ == "__main__":
    app.run()
