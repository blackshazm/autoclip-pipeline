import json
import urllib.request
import time

prompt = '''Você é um copywriter. Responda estritamente com um JSON válido contendo:
- "title": título chamativo com 1 emoji frontal
- "description": descrição curta
- "tags": lista de 4 hashtags

Texto: O convidado revelou que recebia propostas nos bastidores da TV e ninguém desconfiava.'''

models_to_test = ["qwen3.5:4b", "qwen3:8b"]

for m in models_to_test:
    print("\n" + "=" * 50)
    print(f"TESTANDO MODELO: {m}")
    print("=" * 50)
    t0 = time.time()
    data = {
        "model": m,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        res_json = json.loads(resp.read().decode("utf-8"))
        raw = res_json.get("response", "").strip()
        elapsed = round(time.time() - t0, 2)
        print(f"[*] Tempo de resposta: {elapsed}s")
        print(f"[*] Resposta RAW (primeiros 250 caracteres):\n{raw[:250]}\n")
        
        parsed = json.loads(raw)
        print(f"[OK] JSON VÁLIDO! Chaves: {list(parsed.keys())}")
        print(f"     Title: {parsed.get('title')}")
        print(f"     Tags : {parsed.get('tags')}")
    except json.JSONDecodeError as jde:
        print(f"[X] QUEBROU JSON: {jde}")
    except Exception as e:
        print(f"[X] ERRO NA REQUISIÇÃO: {e}")
