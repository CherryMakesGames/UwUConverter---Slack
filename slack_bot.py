import os

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler


BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

app = App(token=BOT_TOKEN)


def main():
    print("UwUConverter Slack bot starting...")
    SocketModeHandler(app, APP_TOKEN).start()


if __name__ == "__main__":
    main()
