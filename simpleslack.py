import slack, os

class Slack():
    def __init__(self):
        self.slack_client = slack.WebClient(token=os.environ['SLACK_CLIENT_SECRET'])
        self.slack_channel = os.environ['SLACK_CHANNEL']

s = Slack()

def send_to_slack(text):
    response = s.slack_client.chat_postMessage(channel = s.slack_channel, text=text)
    assert response["ok"]
    assert response["message"]["text"] == text

    