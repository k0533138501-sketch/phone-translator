from flask import Flask, request, Response
from openai import OpenAI
import os
import json
import tempfile
import urllib.parse
import urllib.request

app = Flask(__name__)
client = OpenAI()

YEMOT_TOKEN = os.environ.get("YEMOT_TOKEN", "")


def get_latest_recording():
    url = (
        "https://www.call2all.co.il/ym/api/GetIVR2Dir"
        "?token=" + urllib.parse.quote(YEMOT_TOKEN, safe=":")
        + "&path=2"
    )

    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))

    print("YEMOT DIR DATA:", data, flush=True)

    if data.get("responseStatus") != "OK":
        raise RuntimeError("GetIVR2Dir failed: " + str(data))

    files = data.get("files", [])

    wav_files = []

    for item in files:
        name = str(item.get("name", ""))
        what = str(item.get("what", ""))

        candidate = name or what

        if candidate.lower().endswith(".wav"):
            filename = candidate.split("/")[-1]
            stem = filename.rsplit(".", 1)[0]

            try:
                number = int(stem)
            except ValueError:
                number = -1

            wav_files.append((number, candidate))

    if not wav_files:
        raise RuntimeError("No WAV recordings found in folder 2")

    wav_files.sort(key=lambda x: x[0])
    latest = wav_files[-1][1]

    if latest.startswith("ivr2:"):
        return latest

    if latest.startswith("/"):
        return "ivr2:" + latest

    if latest.startswith("2/"):
        return "ivr2:/" + latest

    return "ivr2:/2/" + latest


def download_yemot_recording(recording_path):
    url = (
        "https://www.call2all.co.il/ym/api/DownloadFile"
        "?token=" + urllib.parse.quote(YEMOT_TOKEN, safe=":")
        + "&path=" + urllib.parse.quote(recording_path, safe=":/")
    )

    print("DOWNLOADING RECORDING:", recording_path, flush=True)

    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


@app.route("/", methods=["GET", "POST"])
def yemot():
    data = request.values.to_dict()
    print("YEMOT DATA:", data, flush=True)
    call_id = data.get("ApiCallId", "")
if data.get("Replay") == "1" and call_id in last_translations:
    translation = last_translations[call_id]
    return Response(
        f"read=t-{translation}. להאזנה נוספת הקישו אחת.=Replay,,1,1,Digits,yes",
        mimetype="text/plain"
    )

if "Replay" in data and data.get("Replay") != "1":
    return Response(
        "id_list_message=t-תודה",
        mimetype="text/plain"
    )
    if data.get("hangup") == "yes":
        return Response(
            "noop=hangup",
            mimetype="text/plain"
        )

    try:
        print("STEP 1: entered translator try", flush=True)
        if not YEMOT_TOKEN:
            raise RuntimeError("YEMOT_TOKEN is not configured")

        recording_path = get_latest_recording()
        print("STEP 2: got recording path", recording_path, flush=True)
        print("LATEST RECORDING:", recording_path, flush=True)

        audio_bytes = download_yemot_recording(recording_path)
        print("STEP 3: downloaded recording, bytes =", len(audio_bytes), flush=True)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="gpt-4o-mini-transcribe",
                    file=audio_file,
                    language="ru"
                )

            text = transcription.text.strip()
            print("OPENAI TRANSCRIPTION:", text, flush=True)

        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        result = client.responses.create(
            model="gpt-5.6-luna",
            instructions=(
                "Translate the user's Russian text into natural Hebrew. "
                "Return only the Hebrew translation, without explanation."
            ),
            input=text,
            store=False
        )

        translation = result.output_text.strip()

        print("RUSSIAN TEXT:", text, flush=True)
        print("HEBREW TRANSLATION:", translation, flush=True)

       if call_id:
           last_translations[call_id] = translation

       return Response(
           f"read=t-{translation}. להאזנה נוספת הקישו אחת.=Replay,,1,1,Digits,yes",
           mimetype="text/plain"
       )

    except Exception as e:
        print("TRANSLATOR ERROR:", repr(e), flush=True)

        return Response(
            "id_list_message=t-אירעה שגיאה בתרגום",
            mimetype="text/plain"
        )


@app.route("/health", methods=["GET"])
def health():
    return "OK"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
