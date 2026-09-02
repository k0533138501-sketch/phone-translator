from flask import Flask, request, Response
from openai import OpenAI
import os
import json
import tempfile
import urllib.parse
import urllib.request
import requests
import time
import psycopg2
from psycopg2.extras import RealDictCursor
app = Flask(__name__)
client = OpenAI()

YEMOT_TOKEN = os.environ.get("YEMOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
last_translations = {}
study_items = []
study_positions = {}
def get_db():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    if not DATABASE_URL:
        print("DATABASE_URL is not set", flush=True)
        return

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                          CREATE TABLE IF NOT EXISTS study_items (
                              id SERIAL PRIMARY KEY,
                              phone_number TEXT NOT NULL,
                              wav_path TEXT NOT NULL,
                              russian_text TEXT,
                              hebrew_text TEXT,
                              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                              UNIQUE(phone_number, wav_path)
                          )
                      """)
            cur.execute("""
                ALTER TABLE study_items
                ADD COLUMN IF NOT EXISTS phone_number TEXT
            """)

            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS
                study_items_phone_wav_unique
                ON study_items (phone_number, wav_path)
            """)
    print("DATABASE READY", flush=True)
init_db() 
def save_study_item(phone_number, wav_path, russian_text, hebrew_text):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO study_items
                    (phone_number, wav_path, russian_text, hebrew_text)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (phone_number, wav_path) DO NOTHING
            """, (phone_number, wav_path, russian_text, hebrew_text))


def load_study_items(phone_number):
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    id,
                    wav_path AS recording,
                    russian_text,
                    hebrew_text AS translation
                FROM study_items
                WHERE phone_number = %s
                ORDER BY id ASC
            """, (phone_number,))
            return [dict(row) for row in cur.fetchall()]


def delete_study_item(phone_number, item_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM study_items WHERE phone_number = %s AND id = %s",
                (phone_number, item_id)
            )


def delete_all_study_items(phone_number):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM study_items WHERE phone_number = %s",
                (phone_number,)
            )
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
def upload_hebrew_tts_to_yemot(tts_path):
    url = "https://www.call2all.co.il/ym/api/UploadFile"

    with open(tts_path, "rb") as audio_file:
        response = requests.post(
            url,
            data={
                "token": YEMOT_TOKEN,
                "path": "ivr2:/1/000.wav",
                "convertAudio": "1",
            },
            files={
                "file": ("000.wav", audio_file, "audio/wav")
            },
            timeout=30,
        )

    print("HEBREW YEMOT UPLOAD STATUS:", response.status_code, flush=True)
    print("HEBREW YEMOT UPLOAD RESPONSE:", response.text, flush=True)

    return response.text
def create_slow_hebrew_tts_for_study(text):
    tts_path = tempfile.NamedTemporaryFile(
        suffix=".wav",
        delete=False
    ).name

    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="coral",
        input=text,
        instructions="Speak Hebrew extremely slowly. Pronounce every word very slowly and clearly, with long pauses between words. This is for a beginner language learner.",
        response_format="wav"
    ) as speech:
        speech.stream_to_file(tts_path)

    return tts_path
def create_russian_system_tts(text):
    tts_path = tempfile.NamedTemporaryFile(
        suffix=".wav",
        delete=False
    ).name

    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="coral",
        input=text,
        instructions=(
            "Speak in Russian in a warm, calm, professional female voice. "
            "Speak clearly and naturally, at a moderately slow pace. "
            "This is a telephone voice assistant for people learning Hebrew. "
            "Use clear diction and short natural pauses. "
            "Do not sound theatrical or overly emotional."
        ),
        response_format="wav"
    ) as speech:
        speech.stream_to_file(tts_path)

    return tts_path
def upload_system_voice_to_yemot(tts_path, yemot_path):
    url = "https://www.call2all.co.il/ym/api/UploadFile"

    with open(tts_path, "rb") as audio_file:
        response = requests.post(
            url,
            data={
                "token": YEMOT_TOKEN,
                "path": yemot_path,
                "convertAudio": "1",
            },
            files={
                "file": ("voice.wav", audio_file, "audio/wav")
            },
            timeout=30,
        )

    print("SYSTEM VOICE UPLOAD STATUS:", response.status_code, flush=True)
    print("SYSTEM VOICE UPLOAD RESPONSE:", response.text, flush=True)

    return response.text
def generate_test_main_menu():
    text = (
        "Программа голосового перевода и упражнений для изучающих иврит. "
        "Для перевода с русского на иврит нажмите два. "
        "Для упражнений нажмите пять."
    )

    tts_path = create_russian_system_tts(text)

    return upload_system_voice_to_yemot(
        tts_path,
        "ivr2:/99/000.wav"
    )
def generate_all_system_voices():
    messages = {
        "M1000": (
            "Голосовой разговорник. "
            "Для перевода с русского на иврит нажмите два. "
            "Для упражнений нажмите пять."
        ),
                    
        "M2000": (
            "Произнесите фразу на русском языке. "
            "После окончания нажмите решётку."
        ),

       "M2001": (
            "Перевод готов. "
            "Для повторного прослушивания нажмите один. "
            "Для возврата в главное меню нажмите ноль."
        ),
        "M2002": (
            "Не удалось распознать запись. "
            "Попробуйте ещё раз."
        ),

        "M5000": "Режим упражнений.",

        "M5001": "Количество сохранённых упражнений:",

        "M5002": (
            "Сохранённых упражнений нет. "
            "Чтобы добавить упражнение, перейдите в режим два."
        ),

        "M5003": (
            "Для следующего упражнения нажмите один. "
            "Для удаления текущего упражнения нажмите два. "
            "Для повторного прослушивания нажмите три. "
            "Для прослушивания предыдущего упражнения нажмите четыре. "
            "Для возврата в главное меню нажмите ноль."
        ),

        "M5004": "Упражнение удалено.",

        "M5005": "Осталось упражнений:",

        "M5006": (
            "Упражнение удалено. "
            "Сохранённых упражнений больше нет."
        ),

        "M5900": (
            "Внимание! Вы собираетесь удалить все сохранённые упражнения. "
            "Это действие нельзя отменить. "
            "Для подтверждения удаления нажмите девять ещё раз. "
            "Для отмены нажмите ноль."
        ),

        "M5901": "Все сохранённые упражнения удалены.",

        "M5902": "Сохранённых упражнений нет.",

        "M5903": "Удаление отменено.",

        "M9000": (
            "Произошла ошибка. "
            "Попробуйте ещё раз."
        ),
    }

    results = []

    for file_name, text in messages.items():
        tts_path = create_russian_system_tts(text)

        result = upload_system_voice_to_yemot(
            tts_path,
            f"ivr2:/99/{file_name}.wav"
        )

        results.append(f"{file_name}: {result}")

    return "\n".join(results)  
@app.route("/generate-one-voice", methods=["GET"])
def generate_one_voice():
    file_name = request.args.get("file")

    messages = {
        "M1000": (
            "Голосовой разгово́рник. "
            "Для перевода с русского на иврит нажмите два. "
            "Для упражнений нажмите пять."
        ),
        "M2001": (
            "Перевод готов. "
            "Для повторного прослушивания нажмите один. "
            "Для возврата в главное меню нажмите ноль."
        ),
        "M5003": (
            "Для следующего упражнения нажмите один. "
            "Для удаления текущего упражнения нажмите два. "
            "Для повторного прослушивания нажмите три. "
            "Для прослушивания предыдущего упражнения нажмите четыре. "
            "Для возврата в главное меню нажмите ноль."
        ),

        "M5004": "Упражнение удалено.",

        "M5005": "Осталось упражнений:",

        "M5006": (
            "Упражнение удалено. "
            "Сохранённых упражнений больше нет."
        ),

        "M5900": (
            "Внимание! Вы собираетесь удалить все сохранённые упражнения. "
            "Это действие нельзя отменить. "
            "Для подтверждения удаления нажмите девять ещё раз. "
            "Для отмены нажмите ноль."
        ),

        "M5901": "Все сохранённые упражнения удалены.",

        "M5902": "Сохранённых упражнений нет.",

        "M5903": "Удаление отменено.",

        "M9000": (
            "Произошла ошибка. "
            "Попробуйте ещё раз."
        ),
    }

    if file_name not in messages:
        return Response("Unknown file", status=400, mimetype="text/plain")

    tts_path = create_russian_system_tts(messages[file_name])

    if file_name == "M1000":
        yemot_path = "ivr2:/M1000.wav"
    else:
        yemot_path = f"ivr2:/99/{file_name}.wav"
    
    result = upload_system_voice_to_yemot(
        tts_path,
        yemot_path
    )
    
    return Response(result, mimetype="text/plain")    
@app.route("/generate-number-voice", methods=["GET"])
def generate_number_voice():
    number = request.args.get("number", "")

    numbers = {
        "1": "один",
        "2": "два",
        "3": "три",
        "4": "четыре",
        "5": "пять",
        "6": "шесть",
        "7": "семь",
        "8": "восемь",
        "9": "девять",
        "10": "десять",
        "11": "одиннадцать",
        "12": "двенадцать",
        "13": "тринадцать",
        "14": "четырнадцать",
        "15": "пятнадцать",
        "16": "шестнадцать",
        "17": "семнадцать",
        "18": "восемнадцать",
        "19": "девятнадцать",
        "20": "двадцать",
    }

    if number not in numbers:
        return Response(
            "Unknown number",
            status=400,
            mimetype="text/plain"
        )

    tts_path = create_russian_system_tts(numbers[number])

    file_name = f"N{int(number):02d}.wav"

    result = upload_system_voice_to_yemot(
        tts_path,
        f"ivr2:/99/{file_name}"
    )

    return Response(result, mimetype="text/plain")
@app.route("/study", methods=["GET", "POST"])    
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
    if request.path == "/study":
        data.pop("Replay", None)
        if not data.get("Study"):
            data["Study"] = "start"
    print("YEMOT DATA:", data, flush=True)
    call_id = data.get("ApiCallId", "")
    he_ru_mode = request.path == "/he-ru"
    if data.get("Replay") == "5" and data.get("ApiExtension") != "5":
        return Response(
            "go_to_folder=/5",
            mimetype="text/plain"
        )
    print("STUDY VALUE BEFORE BLOCKS:", repr(data.get("Study")), flush=True)
    if data.get("hangup") == "yes":
        print("IGNORING HANGUP CALLBACK", flush=True)
        return Response("", mimetype="text/plain")    
    if data.get("Study") == "start":
        phone_number = data.get("ApiPhone", "")
        print("STUDY DB PHONE:", repr(phone_number), flush=True)
    
        study_items.clear()
        study_items.extend(load_study_items(phone_number))
    
        print(
            "STUDY DB LOADED:",
            len(study_items),
            study_items,
            flush=True
        )
    
        if not study_items:
            return Response(
                "id_list_message=f-/99/M5002&go_to_folder=/",
                mimetype="text/plain"
            )
    
        count = len(study_items)
    
        print("STUDY START COUNT:", count, flush=True)
    
        pos = count - 1
        item = study_items[pos]
        study_positions[call_id] = pos
    
        play_path = item["recording"]
        translation = item["translation"]

        study_tts_path = create_slow_hebrew_tts_for_study(translation)
        upload_hebrew_tts_to_yemot(study_tts_path)
    
        if play_path.startswith("ivr2:"):
            play_path = play_path[5:]
    
        if play_path.lower().endswith(".wav"):
            play_path = play_path[:-4]
    
        if 1 <= count <= 20:
            number_message = f".f-/99/N{count:02d}"
        else:
            number_message = ""
    
        return Response(
            f"id_list_message=f-/99/M5000.f-/99/M5001{number_message}.f-/{play_path}.f-/1/000"
            f"&read=f-/99/M5003=Study,,1,1,20,NO,yes,no,,,,,,InsertLettersTypeChangeNo,no",
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
        study_tts_path = create_slow_hebrew_tts_for_study(translation)
        upload_hebrew_tts_to_yemot(study_tts_path)
        print("STUDY NEXT:", pos, play_path, translation, flush=True)
        if play_path.startswith("ivr2:"):
            play_path = play_path[5:]

        if play_path.lower().endswith(".wav"):
            play_path = play_path[:-4]

        return Response(
            f"id_list_message=f-/{play_path}.f-/1/000&read=f-/99/M5003=Study,,1,1,20,NO,yes,no,,,,,,InsertLettersTypeChangeNo,no",
            mimetype="text/plain"
        )
    if data.get("Study") == "2":
        print("DELETE BLOCK ENTERED:", data, flush=True)
    
        if not study_items:
            return Response(
                "id_list_message=f-/99/M5002&go_to_folder=/",
                mimetype="text/plain"
            )
    
        pos = study_positions.get(call_id, len(study_items) - 1)
    
        if pos >= len(study_items):
            pos = len(study_items) - 1
    
        item = study_items[pos]
        phone_number = data.get("ApiPhone", "")
    
        delete_study_item(phone_number, item["id"])
    
        study_items.clear()
        study_items.extend(load_study_items(phone_number))
    
        count = len(study_items)
    
        print("STUDY COUNT AFTER DELETE:", count, flush=True)
    
        if not study_items:
            study_positions.pop(call_id, None)
    
            return Response(
                "id_list_message=f-/99/M5006&go_to_folder=/",
                mimetype="text/plain"
            )
    
        pos -= 1
    
        if pos < 0:
            pos = len(study_items) - 1
    
        study_positions[call_id] = pos
    
        item = study_items[pos]
        play_path = item["recording"]
        translation = item["translation"]
    
        study_tts_path = create_slow_hebrew_tts_for_study(translation)
        upload_hebrew_tts_to_yemot(study_tts_path)
    
        if play_path.startswith("ivr2:"):
            play_path = play_path[5:]
    
        if play_path.lower().endswith(".wav"):
            play_path = play_path[:-4]
    
        if 1 <= count <= 20:
            number_message = f".f-/99/N{count:02d}"
        else:
            number_message = ""
    
        response_text = (
            f"id_list_message=f-/99/M5004.f-/99/M5005{number_message}"
            f".f-/{play_path}.f-/1/000"
            f"&read=f-/99/M5003=Study,,1,1,20,NO,yes,no,,,,,,InsertLettersTypeChangeNo,no"
        )
    
        print("DELETE RESPONSE:", response_text, flush=True)
    
        return Response(
            response_text,
            mimetype="text/plain"
        ) 
    if data.get("Study") == "3":
        if not study_items:
            return Response(
                "id_list_message=f-/99/M5002&go_to_folder=/",
                mimetype="text/plain"
            )
    
        pos = study_positions.get(call_id, len(study_items) - 1)
    
        if pos >= len(study_items):
            pos = len(study_items) - 1
    
        if pos < 0:
            pos = 0
    
        study_positions[call_id] = pos
    
        item = study_items[pos]
        play_path = item["recording"]
        translation = item["translation"]
    
        study_tts_path = create_slow_hebrew_tts_for_study(translation)
        upload_hebrew_tts_to_yemot(study_tts_path)
    
        if play_path.startswith("ivr2:"):
            play_path = play_path[5:]
    
        if play_path.lower().endswith(".wav"):
            play_path = play_path[:-4]
    
        return Response(
            f"id_list_message=f-{play_path}.f-/1/000"
            f"&read=f-/99/M5003=Study,,1,1,20,NO,yes,no,,,,,,InsertLettersTypeChangeNo,no",
            mimetype="text/plain"
        )
    if data.get("Study") == "4":
        if not study_items:
            return Response(
                "id_list_message=f-/99/M5002&go_to_folder=/",
                mimetype="text/plain"
            )
    
        pos = study_positions.get(call_id, len(study_items) - 1)
    
        pos += 1
    
        if pos >= len(study_items):
            pos = 0
    
        study_positions[call_id] = pos
    
        item = study_items[pos]
        play_path = item["recording"]
        translation = item["translation"]
    
        study_tts_path = create_slow_hebrew_tts_for_study(translation)
        upload_hebrew_tts_to_yemot(study_tts_path)
    
        if play_path.startswith("ivr2:"):
            play_path = play_path[5:]
    
        if play_path.lower().endswith(".wav"):
            play_path = play_path[:-4]
    
        return Response(
            f"id_list_message=f-{play_path}.f-/1/000"
            f"&read=f-/99/M5003=Study,,1,1,20,NO,yes,no,,,,,,InsertLettersTypeChangeNo,no",
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
    
        if not he_ru_mode:
            hebrew_tts_path = create_slow_hebrew_tts_for_study(translation)
            upload_hebrew_tts_to_yemot(hebrew_tts_path)
    
            return Response(
                f"id_list_message=f-{play_path}.f-/1/000"
                "&read=f-/99/M2001=Replay,,1,1,20,NO,yes,no,,,,,,InsertLettersTypeChangeNo,no",
                mimetype="text/plain"
            )
    
        return Response(
            f"id_list_message=f-{play_path}.f-/10/1/000"
            f"&read=f-/99/M2001=Replay,,1,1,20,NO,yes,no,,,,,,InsertLettersTypeChangeNo,no",
            mimetype="text/plain"
        )
       

    if data.get("Replay") == "0":            
        return Response(
            "go_to_folder=/",
            mimetype="text/plain"
        )

    if data.get("hangup") == "yes" and not data.get("Study"):      
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
            phone_number = data.get("ApiPhone", "")
            print("STUDY SAVE PHONE:", repr(phone_number), flush=True)
            save_study_item(
                phone_number,
                recording_path,
                text,
                translation
            )

            study_items.clear()
            study_items.extend(load_study_items(phone_number))

            print("STUDY DB COUNT:", len(study_items), flush=True)
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
        if not he_ru_mode:
            hebrew_tts_path = tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False
            ).name

            with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice="coral",
                input=translation,
                instructions="Speak Hebrew extremely slowly. Pronounce every word very slowly and clearly, with long pauses between words. This is for a beginner language learner.",
                response_format="wav"
            ) as hebrew_speech:
                hebrew_speech.stream_to_file(hebrew_tts_path)

            print("HEBREW TTS FILE:", hebrew_tts_path, flush=True)
            upload_hebrew_tts_to_yemot(hebrew_tts_path) 
            time.sleep(3)
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
        response_text = (
            f"id_list_message=f-{play_path}.f-/10/1/000&read=t-לחזרה הקש אחת. לתפריט הראשי הקש אפס=Replay,,,1,1,20,No"
            if he_ru_mode
            else
            f"id_list_message=f-000&read=f-/99/M2001=Replay,,1,1,20,NO,yes,no,,,,,,InsertLettersTypeChangeNo,no"
        )
    
        print("FINAL YEMOT RESPONSE:", response_text, flush=True)
    
        return Response(
            response_text,
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
