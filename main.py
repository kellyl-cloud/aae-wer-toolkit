from flask import Flask, request, jsonify, send_from_directory
import urllib.request, json, os, base64, requests

app = Flask(__name__, static_folder='.')
OPENAI_KEY = os.environ.get("OPENAI_KEY", "")
ANGO_KEY = os.environ.get("ANGO_KEY", "")
ANGO_BASE = "https://imeritapi.ango.ai"

# CORAAL samples — real AAE sociolinguistic interviews with gold transcripts
CORAAL_SAMPLES = [
    {
        "id": "ATL_se1_ag1_f_01",
        "audio_url": "https://coraal.uoregon.edu/download/ATL/audio/ATL_se1_ag1_f_01.wav",
        "transcript_url": "https://coraal.uoregon.edu/download/ATL/transcripts/ATL_se1_ag1_f_01.txt"
    },
    {
        "id": "DCA_se1_ag1_f_01",
        "audio_url": "https://coraal.uoregon.edu/download/DCA/audio/DCA_se1_ag1_f_01.wav",
        "transcript_url": "https://coraal.uoregon.edu/download/DCA/transcripts/DCA_se1_ag1_f_01.txt"
    },
    {
        "id": "PRV_se1_ag1_f_01",
        "audio_url": "https://coraal.uoregon.edu/download/PRV/audio/PRV_se1_ag1_f_01.wav",
        "transcript_url": "https://coraal.uoregon.edu/download/PRV/transcripts/PRV_se1_ag1_f_01.txt"
    }
]

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/set-keys', methods=['POST','OPTIONS'])
def set_keys():
    global OPENAI_KEY, ANGO_KEY
    if request.method == 'OPTIONS':
        return cors('')
    data = request.json
    OPENAI_KEY = data.get('openaiKey', OPENAI_KEY)
    ANGO_KEY = data.get('angoKey', ANGO_KEY)
    return cors(jsonify({"ok": True}))

@app.route('/coraal-samples')
def coraal_samples():
    return cors(jsonify({"samples": CORAAL_SAMPLES}))

@app.route('/fetch-coraal-transcript')
def fetch_coraal_transcript():
    url = request.args.get('url','')
    try:
        r = requests.get(url, timeout=30)
        lines = r.text.strip().split('\n')
        # CORAAL transcripts have speaker turns — extract just the speech text
        speech = []
        for line in lines:
            parts = line.split('\t')
            if len(parts) >= 4:
                text = parts[3].strip()
                # Remove CORAAL annotation markers
                import re
                text = re.sub(r'\(.*?\)','',text)
                text = re.sub(r'\[.*?\]','',text)
                text = text.strip()
                if text:
                    speech.append(text)
        return cors(jsonify({"transcript": ' '.join(speech)}))
    except Exception as e:
        return cors(jsonify({"error": str(e)})), 500

@app.route('/fetch-audio-b64')
def fetch_audio_b64():
    url = request.args.get('url','')
    is_ango = request.args.get('ango','false') == 'true'
    headers = {"apikey": ANGO_KEY} if is_ango else {}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=55) as r:
            raw = r.read(2 * 1024 * 1024)  # max 2MB
            ct = r.headers.get("Content-Type","audio/wav")
        return cors(jsonify({"base64": base64.b64encode(raw).decode(), "mimeType": ct}))
    except Exception as e:
        return cors(jsonify({"error": str(e)})), 500

@app.route('/transcribe', methods=['POST','OPTIONS'])
def transcribe():
    if request.method == 'OPTIONS':
        return cors('')
    data = request.json
    audio_bytes = base64.b64decode(data['audio'])
    mime = data.get('mimeType','audio/wav')
    fmt = 'mp3' if 'mp3' in mime else 'wav'
    prompt = data.get('prompt', '')
    boundary = b'----B' + os.urandom(4).hex().encode()
    parts  = b'--'+boundary+b'\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n'
    parts += b'--'+boundary+b'\r\nContent-Disposition: form-data; name="response_format"\r\n\r\njson\r\n'
    if prompt:
        parts += b'--'+boundary+b'\r\nContent-Disposition: form-data; name="prompt"\r\n\r\n'+prompt.encode()+b'\r\n'
    parts += b'--'+boundary+b'\r\nContent-Disposition: form-data; name="file"; filename="audio.'+fmt.encode()+b'"\r\nContent-Type: '+mime.encode()+b'\r\n\r\n'+audio_bytes+b'\r\n'
    parts += b'--'+boundary+b'--\r\n'
    req = urllib.request.Request('https://api.openai.com/v1/audio/transcriptions', parts,
        {'Authorization': f'Bearer {OPENAI_KEY}', 'Content-Type': f'multipart/form-data; boundary={boundary.decode()}'})
    try:
        with urllib.request.urlopen(req, timeout=55) as r:
            return cors(jsonify(json.loads(r.read().decode('utf-8'))))
    except urllib.error.HTTPError as e:
        return cors(jsonify({"error": e.read().decode()})), e.code

@app.route('/gpt', methods=['POST','OPTIONS'])
def gpt():
    if request.method == 'OPTIONS':
        return cors('')
    data = request.json
    req = urllib.request.Request('https://api.openai.com/v1/chat/completions',
        json.dumps(data['body']).encode(),
        {'Authorization': f'Bearer {OPENAI_KEY}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=55) as r:
            return cors(jsonify(json.loads(r.read().decode('utf-8'))))
    except urllib.error.HTTPError as e:
        return cors(jsonify({"error": e.read().decode()})), e.code

@app.route('/ango-tasks')
def ango_tasks():
    project = request.args.get('project','')
    page = request.args.get('page','1')
    stage = request.args.get('stage','Complete')
    url = f"{ANGO_BASE}/v2/project/{project}/tasks?page={page}&limit=50&stage={urllib.parse.quote(stage)}"
    req = urllib.request.Request(url, headers={"apikey": ANGO_KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return cors(jsonify(json.loads(r.read())))
    except urllib.error.HTTPError as e:
        return cors(jsonify({"error": e.read().decode()})), e.code

def cors(response):
    from flask import make_response
    import urllib.parse
    if isinstance(response, str):
        response = make_response(response)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
