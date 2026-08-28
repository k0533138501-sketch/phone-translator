from flask import Flask, request, Response
from openai import OpenAI
import os
import json
import tempfile
import urllib.parse
import urllib.request
import requests
import time
app = Flask(__name__)
client = OpenAI()

YEMOT_TOKEN = os.environ.get("YEMOT_TOKEN", "")
last_translations = {}
study_items = []
study_positions = {}
def get_latest_recording(folder="2"):

    url = (
        "https://www.call2all.co.il/ym/api/GetIVR2Dir"
        "?token=" + urllib.parse.quote(YEMOT_TOKEN, safe=":")
        + "&path=" + urllib.parse.quote(str(folder), safe="")
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
       raise RuntimeError("No WAV recordings found in folder " + str(folder))
    wav_files.sort(key=lambda x: x[0])
    print("LATEST WAV CANDIDATES:", wav_files[-5:], flush=True)
    latest = wav_files[-1][1]

    if latest.startswith("ivr2:"):
        return latest

    if latest.startswith("/"):
        return "ivr2:" + latest

    if latest.startswith(str(folder) + "/"):
        return "ivr2:/" + latest

    return "ivr2:/" + str(folder) + "/" + latest


def download_yemot_recording(recording_path):
    url = (
        "https://www.call2all.co.il/ym/api/DownloadFile"
        "?token=" + urllib.parse.quote(YEMOT_TOKEN, safe=":")
        + "&path=" + urllib.parse.quote(recording_path, safe=":/")
    )

    print("DOWNLOADING RECORDING:", recording_path, flush=True)

    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()

def upload_tts_to_yemot(tts_path):
    url = "https://www.call2all.co.il/ym/api/UploadFile"

    with open(tts_path, "rb") as audio_file:
        response = requests.post(
            url,
            data={
                "token": YEMOT_TOKEN,
                "path": "ivr2:/10/1/000.wav",
            },
            files={
                "file": ("000.wav", audio_file, "audio/wav")
            },
            timeout=30,
        )

    print("YEMOT UPLOAD STATUS:", response.status_code, flush=True)
    print("YEMOT UPLOAD RESPONSE:", response.text, flush=True)

    return response.text
@app.route("/", methods=["GET", "POST"])
@app.route("/he-ru", methods=["GET", "POST"])
def yemot():
    if request.method == "HEAD":
        return Response("", status=200, mimetype="text/plain")
    data = request.values.to_dict()
    study_values = request.values.getlist("Study")
    if study_values:
        study_value = study_values[-1]
        if "?" in study_value:
            study_value = study_value.split("?", 1)[0]
        data["Study"] = study_value
    replay_values = request.values.getlist("Replay")
    if replay_values:
        data["Replay"] = replay_values[-1]
    print("YEMOT DATA:", data, flush=True)
    call_id = data.get("ApiCallId", "")
    he_ru_mode = request.path == "/he-ru"
    if data.get("Replay") == "5" and data.get("ApiExtension") != "5":
        return Response(
            "go_to_folder=/5",
            mimetype="text/plain"
        )
      
        
    if data.get("Study") == "start":
        if not study_items:
            return Response(
                "t-Нет сохранённых упражнений",
                mimetype="text/plain"
            )
        print("STUDY START COUNT:", len(study_items), flush=True)
        pos = len(study_items) - 1
        item = study_items[pos]
        study_positions[call_id] = pos
        play_path = item["recording"]
        translation = item["translation"]

        if play_path.startswith("ivr2:"):
            play_path = play_path[5:]

        if play_path.lower().endswith(".wav"):
            play_path = play_path[:-4]

        return Response(
            f"id_list_message=f-/{play_path}.t-{translation}&read=f-000=Study,,1,1,20,No",
            mimetype="text/plain"
        )
    if data.get("Study") == "1":       
        if not study_items:
            return Response(
                "go_to_folder=/",
                mimetype="text/plain"
            )

        pos = study_positions.get(call_id, len(study_items) - 1) - 1

        if pos < 0:
            pos = len(study_items) - 1

        study_positions[call_id] = pos

        item = study_items[pos]
        play_path = item["recording"]
        translation = item["translation"]
        print("STUDY DELETE NEXT:", pos, play_path, translation, flush=True)
        if play_path.startswith("ivr2:"):
            play_path = play_path[5:]

        if play_path.lower().endswith(".wav"):
            play_path = play_path[:-4]

        return Response(
            f"id_list_message=f-/{play_path}.t-{translation}&read=f-000=Study,,1,1,20,No",
            mimetype="text/plain"
        )
        if data.get("Study") == "2":
                if not study_items:
                    return Response(
                        "go_to_folder=/",
                        mimetype="text/plain"
                    )

                pos = study_positions.get(call_id, len(study_items) - 1)

                if pos >= len(study_items):
                    pos = len(study_items) - 1

                study_items.pop(pos)

                if not study_items:
                    study_positions.pop(call_id, None)
                    return Response(
                        "go_to_folder=/",
                        mimetype="text/plain"
                    )

                if pos >= len(study_items):
                    pos = len(study_items) - 1

                study_positions[call_id] = pos

                item = study_items[pos]
                play_path = item["recording"]
                translation = item["translation"]

                if play_path.startswith("ivr2:"):
                    play_path = play_path[5:]

                if play_path.lower().endswith(".wav"):
                    play_path = play_path[:-4]

                return Response(
                    f"id_list_message=f-/{play_path}.t-{translation}&read=f-000=Study,,1,1,20,No",
                    mimetype="text/plain"
                )
    if data.get("Study") == "0":
        study_positions.pop(call_id, None)
        return Response(
            "go_to_folder=/",
            mimetype="text/plain"
        )
    if data.get("Replay") == "1" and call_id in last_translations:
        saved = last_translations[call_id]
        recording = saved["recording"]
        translation = saved["translation"]

        play_path = recording

        if play_path.startswith("ivr2:"):
            play_path = play_path[5:]

        if play_path.lower().endswith(".wav"):
            play_path = play_path[:-4]

        return Response(
            (
                f"read=f-{play_path}.f-/10/1/000=Replay,,1,1,20,No"
                if he_ru_mode
                else f"read=f-{play_path}.t-{translation}=Replay,,1,1,20,No"
            ),
            mimetype="text/plain"
        )

    if data.get("Replay") == "0":            
        return Response(
            "go_to_folder=/",
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
        time.sleep(1)
        recording_path = get_latest_recording("10" if he_ru_mode else "2")
        

        
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
                    model="gpt-4o-transcribe",
                    file=audio_file,
                    language="he" if he_ru_mode else "ru",
                    prompt="Transcribe the spoken Hebrew exactly as heard. Do not translate it." if he_ru_mode else "Transcribe the spoken Russian exactly as heard. Do not translate it."
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
                "Translate the user's Hebrew text into natural Russian. "
                "Return only the Russian translation, without explanation."
                if he_ru_mode
                else
                "Translate the user's Russian text into natural Hebrew. "
                "Return only the Hebrew translation, without explanation."
            ),
            input=text,
            store=False
        )

        translation = result.output_text.strip()
        if not he_ru_mode:
            if not any(item["recording"] == recording_path for item in study_items):
                study_items.append({
                    "recording": recording_path,
                    "translation": translation
                })
            print("STUDY APPEND COUNT:", len(study_items), flush=True)
        if he_ru_mode:
            tts_path = tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False
            ).name

            with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice="coral",
                input=translation,
                instructions="Speak clearly in natural Russian.",
                response_format="wav"
            ) as speech:
             speech.stream_to_file(tts_path)

            print("RUSSIAN TTS FILE:", tts_path, flush=True)
            upload_tts_to_yemot(tts_path)
        print("RUSSIAN TEXT:", text, flush=True)
        print("HEBREW TRANSLATION:", translation, flush=True)

        if call_id:
            last_translations[call_id] = {
                "recording": recording_path,
                "translation": translation
            }
        play_path = recording_path

        if play_path.startswith("ivr2:"):
            play_path = play_path[5:]

        if play_path.lower().endswith(".wav"):
            play_path = play_path[:-4]
        return Response(
            f"id_list_message=f-{play_path}.f-/10/1/000&read=t-לחזרה הקש אחת. לתפריט הראשי הקש אפס=Replay,,1,1,20,No" if he_ru_mode else f"read=t-{translation}=Replay,,1,1,20,No",
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
