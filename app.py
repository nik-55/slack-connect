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
    Endpoint to post a message to Slack in a thread and save author information.
    Expects JSON payload: { "message": "your_message", "author": "author_name" }
    """
    try:
        data = request.json
        channel = CHANNEL_NAME
        message = data.get("message")
        author_name = data.get("author")

        if not channel or not message or not author_name:
            return jsonify({"error": "Missing channel, message, or author"}), 400

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()

            # Check if the author exists
            cursor.execute(
                """
            SELECT id, thread_ts FROM authors WHERE name = ?
            """,
                (author_name,),
            )
            author = cursor.fetchone()

            if author:
                author_id, thread_ts = author
            else:
                # Create the author and start a new thread
                response = slack_client.chat_postMessage(
                    channel=channel,
                    text=f"Thread for {author_name}",
                )
                thread_ts = response["ts"]
                cursor.execute(
                    """
                INSERT INTO authors (name, thread_ts)
                VALUES (?, ?)
                """,
                    (author_name, thread_ts),
                )
                author_id = cursor.lastrowid

            # Post the message in the thread
            response = slack_client.chat_postMessage(
                channel=channel, text=message, thread_ts=thread_ts
            )

            # Save the message
            cursor.execute(
                """
            INSERT INTO messages (author_id, message, bot)
            VALUES (?, ?, ?)
            """,
                (author_id, message, False),
            )
            conn.commit()

        return jsonify({"ok": True, "message_ts": response["ts"]})

    except SlackApiError as e:
        return jsonify({"error": str(e.response["error"])}), 500


@app.route("/slack/events", methods=["POST"])
def slack_events():
    """
    Endpoint to listen to Slack events and save Slack messages in the appropriate thread.
    """
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        return jsonify({"error": "Invalid request signature"}), 400

    event_data = request.json

    # Slack URL verification
    if "challenge" in event_data:
        return jsonify({"challenge": event_data["challenge"]})

    # Process events
    if "event" in event_data:
        event = event_data["event"]
        event_type = event.get("type")
        text = event.get("text")
        thread_ts = event.get("thread_ts")
        bot_id = event.get("bot_id")

        # Ignore bot messages
        if bot_id:
            return jsonify({"ok": True})

        if event_type == "message" and text:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()

                # If the message is in a thread, find the associated author
                if thread_ts:
                    cursor.execute(
                        """
                    SELECT id FROM authors WHERE thread_ts = ?
                    """,
                        (thread_ts,),
                    )
                    author_record = cursor.fetchone()

                    if author_record:
                        author_id = author_record[0]

                        # Save the message to the database
                        cursor.execute(
                            """
                        INSERT INTO messages (author_id, message, bot)
                        VALUES (?, ?, ?)
                        """,
                            (author_id, text, False),
                        )
                        conn.commit()

    return jsonify({"ok": True})


@app.route("/history/<author>", methods=["GET"])
def history(author):
    """
    Endpoint to retrieve all messages for a specific author.
    """
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        # Fetch author information
        cursor.execute("SELECT id FROM authors WHERE name = ?", (author,))
        author_record = cursor.fetchone()
        if not author_record:
            return jsonify({"error": "Author not found"}), 404
        author_id = author_record[0]

        # Fetch messages
        cursor.execute(
            """
        SELECT message, bot, timestamp FROM messages WHERE author_id = ?
        """,
            (author_id,),
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
