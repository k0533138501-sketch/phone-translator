from flask import Flask, request, Response
from openai import OpenAI

app = Flask(__name__)
client = OpenAI()


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

    # Первый запрос: просим абонента сказать фразу по-русски
    if "SpeechRecognition" not in data:
        return Response(
            "read=t-Скажите слово или короткое предложение по-русски.=SpeechRecognition,,voice,ru-RU,no",
            mimetype="text/plain"
        )

    # Распознанная русская речь
    text = data.get("SpeechRecognition", "").strip()
    print("RECOGNIZED TEXT:", text, flush=True)

    try:
        result = client.responses.create(
            model="gpt-5.6-luna",
            instructions=(
                "Translate the user's Russian text into natural Hebrew. "
                "Return only the Hebrew translation, with no explanation."
            ),
            input=text,
            store=False
        )

        translation = result.output_text.strip()
        print("HEBREW TRANSLATION:", translation, flush=True)

        # Пока НЕ произносим перевод.
        # Сначала проверяем, что OpenAI правильно переводит.
        return Response(
            "id_list_message=t-התרגום התקבל בהצלחה.",
            mimetype="text/plain"
        )

    except Exception as e:
        print("OPENAI ERROR:", repr(e), flush=True)

        return Response(
            "id_list_message=t-אירעה שגיאה בתרגום.",
            mimetype="text/plain"
        )


@app.route("/health", methods=["GET"])
def health():
    return "OK"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
