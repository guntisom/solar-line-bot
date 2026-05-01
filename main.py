import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    ApiClient, Configuration, MessagingApi, ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
from dotenv import load_dotenv
import advisor

load_dotenv()

app = FastAPI()

configuration = Configuration(access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))


@app.api_route("/", methods=["GET", "HEAD"])
def health():
    return {"status": "Solar LINE bot is running"}


@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    print(f"DEBUG signature: {signature[:20]}...")
    print(f"DEBUG secret: {os.getenv('LINE_CHANNEL_SECRET')}")
    try:
        handler.handle(body.decode(), signature)
    except InvalidSignatureError as e:
        print(f"DEBUG InvalidSignatureError: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print(f"DEBUG unexpected error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text

    reply_text = advisor.chat(user_id, user_message)

    # LINE has a 5000 char limit per message — split if needed
    chunks = [reply_text[i:i+4500] for i in range(0, len(reply_text), 4500)]
    messages = [TextMessage(text=chunk) for chunk in chunks]

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=event.reply_token, messages=messages[:5])
        )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
