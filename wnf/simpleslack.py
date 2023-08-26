import slack

from wnf.scraper import Configure


class Slack(Configure):
    def __init__(self):
        super().__init__()
        self.slack_client = slack.WebClient(token=self.config("slack_client_secret"))
        self.slack_channel = self.config("slack_channel")


s = Slack()


def send_to_slack(text: str):
    response = s.slack_client.chat_postMessage(channel=s.slack_channel, text=text)
    assert response["ok"]
