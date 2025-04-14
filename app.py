from flask import Flask, request, abort
import os

app = Flask(__name__)

@app.route("/callback", methods=['POST'])
def callback():
    # 印出 webhook 傳進來的內容
    body = request.get_data(as_text=True)
    print("🔧 收到 LINE webhook 訊息：", body)

    return 'OK'

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
