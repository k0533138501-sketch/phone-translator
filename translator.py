from flask import Flask, request, Response

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def yemot():
    # Показываем в журнале Render всё, что прислал Yemot
    print("YEMOT DATA:", request.values.to_dict(), flush=True)

    # Первый запрос: просим абонента произнести фразу
    if "SpeechRecognition" not in request.values:
        return Response(
            "read=t-Скажите слово или короткое предложение по-русски.=voice",
            mimetype="text/plain"
        )

    # После распознавания речи
    text = request.values.get("SpeechRecognition", "")
    print("RECOGNIZED TEXT:", text, flush=True)

    return Response(
        "id_list_message=t-Речь получена. Спасибо.",
        mimetype="text/plain"
    )


@app.route("/health", methods=["GET"])
def health():
    return "OK"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
