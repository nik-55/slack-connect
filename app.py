from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Slack configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

slack_client = WebClient(token=SLACK_BOT_TOKEN)
signature_verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

@app.route('/post-message', methods=['POST'])
def post_message():
    """
    Endpoint to post a message to Slack.
    Expects JSON payload: { "channel": "channel_name", "message": "your_message" }
    """
    try:
        data = request.json
        channel = data.get('channel')
        message = data.get('message')

        if not channel or not message:
            return jsonify({'error': 'Missing channel or message'}), 400

        response = slack_client.chat_postMessage(channel=channel, text=message)
        return jsonify({'ok': True, 'message_ts': response['ts']})

    except SlackApiError as e:
        return jsonify({'error': str(e.response['error'])}), 500

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """
    Endpoint to listen to Slack events.
    """
    # Verify the request signature
    if not signature_verifier.is_valid_request(request.get_data(), request.headers):
        return jsonify({'error': 'Invalid request signature'}), 400

    event_data = request.json

    # Handle Slack challenge during URL verification
    if 'challenge' in event_data:
        return jsonify({'challenge': event_data['challenge']})

    # Process events
    if 'event' in event_data:
        event = event_data['event']
        event_type = event.get('type')
        user = event.get('user')
        text = event.get('text')
        channel = event.get('channel')
        bot_id = event.get('bot_id')  # Identify if the message was sent by a bot

        # Ignore events from bots, including this bot
        if bot_id:
            return jsonify({'ok': True})

        # Example: Respond to a specific event
        if event_type == 'message' and user and text:
            try:
                slack_client.chat_postMessage(
                    channel=channel,
                    text=f"This is working: {text}"
                )
            except SlackApiError as e:
                print(f"Error responding to message: {e.response['error']}")

    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(port=5000, debug=True, host='0.0.0.0')
