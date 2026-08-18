from flask import Flask, request, Response

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def yemot():
    data = request.values.to_dict()
    print("YEMOT DATA:", data, flush=True)

    # Служебное сообщение Yemot после завершения звонка
    if data.get("hangup") == "yes":
        return Response(
            "noop=hangup",
            mimetype="text/plain"
        )

    # Первый запрос: просим произнести русскую фразу.
    # ru-RU задаёт русский язык распознавания.
    if "SpeechRecognition" not in data:
        return Response(
            "read=t-Скажите слово или короткое предложение по-русски.=SpeechRecognition,,voice,ru-RU,no",
            mimetype="text/plain"
        )

    # Получили распознанную речь
    text = data.get("SpeechRecognition", "")
    print("RECOGNIZED TEXT:", text, flush=True)

    # Пока только подтверждаем успешный приём.
    # Ответ специально на иврите, чтобы не было проблемы
    # с русским TTS в текущей настройке Yemot.
    return Response(
        "id_list_message=t-הדיבור התקבל בהצלחה",
        mimetype="text/plain"
    )

@app.route("/health", methods=["GET"])
def health():
    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
