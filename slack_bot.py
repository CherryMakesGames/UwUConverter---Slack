import os
import pathlib
import shlex
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import zipfile

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler


BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

MAX_FILE_MB = int(os.environ.get("UWU_MAX_FILE_MB", "200"))
CLI_TIMEOUT = int(os.environ.get("UWU_TIMEOUT_SECONDS", "1800"))
CLI_OVERRIDE = os.environ.get("UWU_CLI_PATH")

app = App(token=BOT_TOKEN)

_recent_files = {}
_recent_files_lock = threading.Lock()


def find_cli():
    if CLI_OVERRIDE:
        candidate = pathlib.Path(CLI_OVERRIDE).expanduser()
        if candidate.is_file():
            return str(candidate)
        raise FileNotFoundError(
            f"UWU_CLI_PATH does not exist: {candidate}"
        )

    found = shutil.which("UwUConverter")
    if found:
        return found

    found = shutil.which("UwUConverter.exe")
    if found:
        return found

    raise FileNotFoundError(
        "UwUConverter CLI was not found in PATH. "
        "Install UwUConverter or set UWU_CLI_PATH."
    )


def run_cli(arguments, cwd=None):
    command = [
        find_cli(),
        *[str(argument) for argument in arguments],
    ]

    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=CLI_TIMEOUT,
        check=False,
    )

    if result.returncode != 0:
        output = "\n".join(
            part.strip()
            for part in (result.stdout, result.stderr)
            if part and part.strip()
        )

        raise RuntimeError(
            output
            or f"UwUConverter exited with code {result.returncode}"
        )

    return result.stdout.strip()


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
            or _recent_files.get((None, user_id, channel_id))
            or _recent_files.get((None, user_id, None))
        )


def safe_filename(name):
    cleaned = pathlib.Path(name or "slack-file").name

    if cleaned in {"", ".", ".."}:
        return "slack-file"

    return cleaned


def download_slack_file(client, file_id, destination):
    response = client.files_info(file=file_id)
    info = response["file"]

    size = int(info.get("size") or 0)
    max_bytes = MAX_FILE_MB * 1024 * 1024

    if size > max_bytes:
        raise ValueError(
            f"File is {size / 1024 / 1024:.1f} MB. "
            f"The bot limit is {MAX_FILE_MB} MB."
        )

    url = (
        info.get("url_private_download")
        or info.get("url_private")
    )

    if not url:
        raise ValueError(
            "Slack did not provide a downloadable URL for this file."
        )

    filename = safe_filename(
        info.get("name") or info.get("title")
    )

    output = pathlib.Path(destination) / filename

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {BOT_TOKEN}",
            "User-Agent": "UwUConverter-Slack-Bot",
        },
    )

    with urllib.request.urlopen(request, timeout=120) as source:
        with output.open("wb") as target:
            shutil.copyfileobj(source, target)

    return output


def upload_result(client, channel_id, path, comment):
    path = pathlib.Path(path)

    client.files_upload_v2(
        file=str(path),
        filename=path.name,
        title=path.name,
        channel=channel_id,
        initial_comment=comment,
    )


def zip_folder(folder, output_path):
    folder = pathlib.Path(folder)
    output_path = pathlib.Path(output_path)

    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for path in folder.rglob("*"):
            if path.is_file():
                archive.write(
                    path,
                    arcname=path.relative_to(folder),
                )

    return output_path


def result_path_from_stdout(stdout):
    lines = [
        line.strip().strip('"')
        for line in stdout.splitlines()
        if line.strip()
    ]

    for line in reversed(lines):
        candidate = pathlib.Path(line)

        if candidate.exists():
            return candidate

    raise RuntimeError(
        "UwUConverter finished, but the bot could not "
        "determine the output path."
    )


def format_help():
    return (
        "*UwUConverter Slack bot*\n"
        "`/uwu convert <format>`\n"
        "`/uwu help`"
    )


def post_error(client, channel_id, user_id, error):
    message = str(error)

    if len(message) > 2500:
        message = message[-2500:]

    try:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=f"UwUConverter failed:\n```{message}```",
        )
    except Exception:
        client.chat_postMessage(
            channel=channel_id,
            text=f"UwUConverter failed:\n```{message}```",
        )


def process_convert(client, channel_id, input_path, args, job_dir):
    if len(args) != 1:
        raise ValueError(
            "Usage: /uwu convert <format>"
        )

    output_format = args[0].lower().lstrip(".")
    output = (
        pathlib.Path(job_dir)
        / f"{input_path.stem}.{output_format}"
    )

    run_cli(
        [
            "convert",
            input_path,
            "--to",
            output_format,
            "--output",
            output,
            "--force",
        ]
    )

    upload_result(
        client,
        channel_id,
        output,
        f"Converted `{input_path.name}` to `{output_format}`.",
    )


@app.command("/uwu")
def handle_uwu_command(ack, body, client, respond):
    ack()

    text = (body.get("text") or "").strip()

    if not text or text.lower() == "help":
        respond(
            response_type="ephemeral",
            text=format_help(),
        )
        return

    parts = text.split()

    if parts[0].lower() != "convert" or len(parts) != 2:
        respond(
            response_type="ephemeral",
            text="Usage: /uwu convert <format>",
        )
        return

    team_id = body.get("team_id")
    user_id = body["user_id"]
    channel_id = body["channel_id"]

    file_id = latest_file_id(
        team_id,
        user_id,
        channel_id,
    )

    if not file_id:
        respond(
            response_type="ephemeral",
            text="Upload a file first.",
        )
        return

    try:
        with tempfile.TemporaryDirectory(
            prefix="uwu-slack-"
        ) as temp_dir:
            input_path = download_slack_file(
                client,
                file_id,
                temp_dir,
            )

            process_convert(
                client,
                channel_id,
                input_path,
                parts[1:],
                temp_dir,
            )

    except Exception as error:
        post_error(
            client,
            channel_id,
            user_id,
            error,
        )


@app.event("file_shared")
def handle_file_shared(event, client):
    file_id = (
        event.get("file_id")
        or (event.get("file") or {}).get("id")
    )

    if not file_id:
        return

    try:
        response = client.files_info(file=file_id)
        file_info = response["file"]

        user_id = event.get("user_id") or file_info.get("user")
        channel_id = event.get("channel_id")

        if not user_id:
            return

        remember_file(
            None,
            user_id,
            channel_id,
            file_id,
        )

    except Exception as error:
        print(error)


@app.command("/uwuconverter-ping")
def uwuconverter_ping(ack, respond):
    ack()
    respond("UwUConverter is online! :3")


def main():
    print("UwUConverter Slack bot starting...")
    SocketModeHandler(app, APP_TOKEN).start()


if __name__ == "__main__":
    main()