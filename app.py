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

# 初始化 Log
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# LINE 與 OpenAI 初始化
line_bot_api = LineBotApi(os.environ.get("LINE_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
openai.api_key = os.environ.get("OPENAI_API_KEY")
OCR_API_KEY = os.environ.get("OCR_API_KEY")

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    logger.info("收到 LINE Webhook 請求")
    logger.info(f"Headers: {request.headers}")
    logger.info(f"Body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("簽名驗證失敗。")
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text
    logger.info(f"收到文字訊息: {user_text}")

    try:
        gpt_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": user_text}]
        )
        reply_text = gpt_response['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"回覆文字訊息時錯誤: {e}")
        reply_text = "發生錯誤，請稍後再試。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    logger.info("📩 收到圖片訊息，開始處理圖片...")

    try:
        message_content = line_bot_api.get_message_content(event.message.id)
        image_data = message_content.content
        temp_file_path = f"/tmp/{event.message.id}.jpg"
        with open(temp_file_path, "wb") as f:
            f.write(image_data)

        logger.info(f"✅ 圖片下載成功: {temp_file_path}")

        # 上傳到 OCR.Space 辨識
        with open(temp_file_path, 'rb') as img:
            response = requests.post(
                'https://api.ocr.space/parse/image',
                files={'filename': img},
                data={'apikey': OCR_API_KEY, 'language': 'eng'}
            )
        result = response.json()
        parsed_text = result["ParsedResults"][0]["ParsedText"]
        logger.info(f"🧠 OCR 辨識結果: {parsed_text.strip()}")

        # 語言判斷
        try:
            lang = detect(parsed_text)
            logger.info(f"🌐 偵測語言: {lang}")
        except Exception as e:
            logger.warning(f"語言偵測失敗: {e}")
            lang = "unknown"

        # 翻譯文字（非中英文才翻）
        translated_text = parsed_text
        if lang not in ["zh-cn", "zh-tw", "en"]:
            try:
                translated_text = GoogleTranslator(source='auto', target='zh-tw').translate(parsed_text)
                logger.info(f"🌏 翻譯後文字: {translated_text}")
            except Exception as e:
                logger.warning(f"翻譯時發生錯誤: {e}")
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"辨識成功，但翻譯過程發生錯誤。\n原始文字：\n{parsed_text}")
                )
                return

        # 使用 GPT 分析文字內容
        try:
            gpt_response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": f"請根據這段 OCR 辨識文字，提供有幫助的說明：\n{translated_text}"}]
            )
            gpt_text = gpt_response["choices"][0]["message"]["content"]
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=gpt_text)
            )
        except Exception as e:
            logger.error(f"GPT 回覆時錯誤: {e}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="辨識成功，但 GPT 回覆過程發生錯誤。")
            )
    except Exception as e:
        logger.error(f"處理圖片時發生錯誤: {e}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="處理圖片時發生錯誤，請稍後再試。")
        )
