import os
import threading

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler


BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

app = App(token=BOT_TOKEN)

_recent_files = {}
_recent_files_lock = threading.Lock()


def remember_file(team_id, user_id, channel_id, file_id):
    if not user_id or not file_id:
        return

    with _recent_files_lock:
        _recent_files[(team_id, user_id, channel_id)] = file_id
        _recent_files[(team_id, user_id, None)] = file_id


def latest_file_id(team_id, user_id, channel_id):
    with _recent_files_lock:
        return (
            _recent_files.get((team_id, user_id, channel_id))
            or _recent_files.get((team_id, user_id, None))
        )


@app.event("file_shared")
def handle_file_shared(event):
    remember_file(
        event.get("team_id"),
        event.get("user_id"),
        event.get("channel_id"),
        event.get("file_id")
        or (event.get("file") or {}).get("id"),
    )


def main():
    print("UwUConverter Slack bot starting...")
    SocketModeHandler(app, APP_TOKEN).start()


if __name__ == "__main__":
    main()
