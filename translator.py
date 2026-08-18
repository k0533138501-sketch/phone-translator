from flask import Flask, request, Response
from openai import OpenAI
import os
import tempfile
import urllib.parse
import urllib.request

app = Flask(__name__)
client = OpenAI()

YEMOT_TOKEN = os.environ.get("YEMOT_TOKEN", "")


def download_yemot_recording(recording_path):
    path = recording_path.strip()

    # Yemot DownloadFile ожидает путь вида ivr2:/...
    if not path.startswith("ivr2:"):
        if not path.startswith("/"):
            path = "/" + path
        path = "ivr2:" + path

    url = (
        "https://www.call2all.co.il/ym/api/DownloadFile"
        "?token=" + urllib.parse.quote(YEMOT_TOKEN, safe=":")
        + "&path=" + urllib.parse.quote(path, safe=":/")
    )

    print("DOWNLOADING RECORDING:", path, flush=True)

    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


@app.route("/", methods=["GET", "POST"])
def yemot():
    data = request.values.to_dict()
    print("YEMOT DATA:", data, flush=True)

    # Служебный запрос после завершения звонка
    if data.get("hangup") == "yes":
        return Response(
            "noop=hangup",
            mimetype="text/plain"
        )

    # Первый запрос: Yemot только записывает голос.
    # Никакого распознавания русского языка в Yemot.
    if "Recording" not in data:
        return Response(
            "read=t-Скажите слово или короткое предложение по-русски. "
            "Для окончания нажмите решётку.=Recording,,record",
            mimetype="text/plain"
        )

    recording_path = data.get("Recording", "")
    print("RECORDING PATH:", recording_path, flush=True)

    try:
        if not YEMOT_TOKEN:
            raise RuntimeError("YEMOT_TOKEN is not configured")

        # Получаем настоящий аудиофайл из Yemot
        audio_bytes = download_yemot_recording(recording_path)

        # Сохраняем временно как WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            # OpenAI распознаёт речь
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

        # Переводим распознанный русский текст на иврит
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

        # Пока только сообщаем об успешном переводе.
        # Сам перевод следующим этапом заставим телефон произнести вслух.
        return Response(
            "id_list_message=t-התרגום התקבל בהצלחה",
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
