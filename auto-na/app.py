from flask import Flask, render_template, request, jsonify
import json, os, threading

app = Flask(__name__)

_status = {
    "running": False,
    "progress": 0,
    "total": 0,
    "current_id": "",
    "log": [],
    "stop_requested": False
}

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_config(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route('/')
def index():
    config = load_config()
    return render_template('index.html', config=json.dumps(config, ensure_ascii=False))


@app.route('/run', methods=['POST'])
def run():
    global _status
    if _status['running']:
        return jsonify({"error": "実行中です。停止してから再実行してください。"})

    data = request.json
    config = data.get('config', {})
    ids = data.get('ids', [])

    if not ids:
        return jsonify({"error": "IDリストが空です。CSVを読み込んでください。"})

    save_config(config)

    _status = {
        "running": True,
        "progress": 0,
        "total": len(ids),
        "current_id": "",
        "log": ["▶ 自動登録を開始します..."],
        "stop_requested": False
    }

    def _thread():
        import asyncio
        from auto import run_automation
        asyncio.run(run_automation(config, ids, _status))

    threading.Thread(target=_thread, daemon=True).start()
    return jsonify({"ok": True})


@app.route('/status')
def status():
    return jsonify(_status)


@app.route('/stop', methods=['POST'])
def stop():
    _status['stop_requested'] = True
    return jsonify({"ok": True})


if __name__ == '__main__':
    print("=" * 50)
    print("対応・NA 一括登録ツール")
    print("ブラウザで http://localhost:5000 を開いてください")
    print("=" * 50)
    app.run(port=5000, debug=False)
