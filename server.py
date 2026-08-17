from flask import Flask, Response

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def yemot():
    return Response(
        "id_list_message=t-הקשר עם השרת פועל",
        mimetype="text/plain"
    )

@app.route("/health", methods=["GET"])
def health():
    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
