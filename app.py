from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier
import os
from dotenv import load_dotenv
import sqlite3

from db import init_db, DATABASE

load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Slack configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
CHANNEL_NAME = "#helpdesk"

slack_client = WebClient(token=SLACK_BOT_TOKEN)
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

# Initialize SQLite database
init_db()


@app.route("/post-message", methods=["POST"])
def post_message():
    """
    Endpoint to post a message to Slack and save author information.
    Expects JSON payload: { "message": "your_message", "author": "author_name" }
    """
    try:
        data = request.json
        channel = CHANNEL_NAME
        message = data.get("message")
        author = data.get("author")

        if not channel or not message or not author:
            return jsonify({"error": "Missing channel, message, or author"}), 400

        # Post message to Slack
        response = slack_client.chat_postMessage(
            channel=channel, text=f"{author}: {message}"
        )

        # Save the message in the database
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO messages (author, message)
                VALUES (?, ?)
            """,
                (author, message),
            )
            conn.commit()

        return jsonify({"ok": True, "message_ts": response["ts"]})

    except SlackApiError as e:
        return jsonify({"error": str(e.response["error"])}), 500


@app.route("/slack/events", methods=["POST"])
def slack_events():
    """
    Endpoint to listen to Slack events and save Slack messages intended for specific authors.
    """
    # Verify the request signature
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        return jsonify({"error": "Invalid request signature"}), 400

    event_data = request.json

    # Handle Slack challenge during URL verification
    if "challenge" in event_data:
        return jsonify({"challenge": event_data["challenge"]})

    # Process events
    if "event" in event_data:
        event = event_data["event"]
        event_type = event.get("type")
        text = event.get("text")
        channel = event.get("channel")
        # channel _name = event.get("channel_name")
        bot_id = event.get("bot_id")  # Identify if the message was sent by a bot

        # Ignore events from bots, including this bot
        if bot_id:
            return jsonify({"ok": True})

        # Look for messages starting with @<author-name>
        if event_type == "message" and text:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT author FROM messages")
                authors = [row[0] for row in cursor.fetchall()]

                for author in authors:
                    if text.startswith(f"&lt;&lt;{author}"):
                        text = text.replace(f"&lt;&lt;{author}", "").strip()
                        # Save the Slack response in the database
                        cursor.execute(
                            """
                            INSERT INTO messages (author, message, bot)
                            VALUES (?, ?, ?)
                        """,
                            (author, text, True),
                        )
                        conn.commit()
                        break

    return jsonify({"ok": True})


@app.route("/history/<author>", methods=["GET"])
def history(author):
    """
    Endpoint to retrieve all messages for a specific author.
    """
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        # Fetch messages
        cursor.execute(
            """
            SELECT message, bot, timestamp FROM messages WHERE author = ?
        """,
            (author,),
        )
        messages = [
            {"message": row[0], "bot": row[1], "timestamp": row[2]}
            for row in cursor.fetchall()
        ]

    if not messages:
        return jsonify({"error": "No history found for this author"}), 404

    return jsonify({"author": author, "messages": messages})


if __name__ == "__main__":
    app.run(port=5000, debug=True, host="0.0.0.0")
