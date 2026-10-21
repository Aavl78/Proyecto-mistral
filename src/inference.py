"""Script de inferencia contra un servidor local de Ollama.

Uso:
  python src/inference.py --model ministral-3:8b --prompt "Hola"
  python src/inference.py --model ministral-3:8b --prompts-file prompts/suite.json --temperature 0.2

Mide TTFT (tiempo al primer token) y tokens/s, y guarda CSV en results/.
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

import requests

# El host se toma de una variable de entorno (sin rutas ni credenciales en el código)
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def parse_args():
    p = argparse.ArgumentParser(description="Inferencia local con Ollama")
    p.add_argument("--model", required=True, help="Nombre del modelo (ver 'ollama list')")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--prompt", help="Un prompt directo")
    g.add_argument("--prompts-file", help="Archivo JSON con la suite de prompts")
    p.add_argument("--temperature", type=float, default=0.7, help="Temperatura de muestreo")
    p.add_argument("--max-tokens", type=int, default=256, help="Máximo de tokens a generar")
    p.add_argument("--output-dir", default="results", help="Carpeta de resultados")
    p.add_argument("--tag", default="", help="Etiqueta para el nombre del archivo (ej. q4, docker)")
    return p.parse_args()


def generate(model, prompt, temperature, max_tokens):
    """Envía un prompt en modo streaming y devuelve texto y métricas."""
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    start = time.perf_counter()
    ttft = None
    text = ""
    final = {}

    try:
        with requests.post(url, json=payload, stream=True, timeout=300) as r:
            if r.status_code == 404:
                raise RuntimeError(f"Modelo '{model}' no encontrado. Use 'ollama list' o 'ollama pull {model}'.")
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                piece = chunk.get("response", "")
                if piece and ttft is None:
                    ttft = time.perf_counter() - start  # primer token recibido
                text += piece
                if chunk.get("done"):
                    final = chunk
    except requests.exceptions.ConnectionError:
        raise RuntimeError(f"No se pudo conectar a Ollama en {OLLAMA_HOST}. ¿Está corriendo el servidor?")

    total = time.perf_counter() - start
    tokens = final.get("eval_count", 0)
    eval_ns = final.get("eval_duration", 0)
    tps = tokens / (eval_ns / 1e9) if eval_ns else 0.0
    return {
        "output": text,
        "tokens": tokens,
        "ttft_s": round(ttft or 0, 3),
        "total_s": round(total, 3),
        "tokens_per_s": round(tps, 2),
    }


def load_prompts(args):
    if args.prompt:
        return [{"id": "manual", "category": "manual", "prompt": args.prompt}]
    try:
        with open(args.prompts_file, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"No existe el archivo de prompts: {args.prompts_file}")


def main():
    args = parse_args()
    try:
        prompts = load_prompts(args)
        rows = []
        for item in prompts:
            print(f"[{item['id']}] {item['category']} ...", flush=True)
            m = generate(args.model, item["prompt"], args.temperature, args.max_tokens)
            print(f"  TTFT={m['ttft_s']}s  tok/s={m['tokens_per_s']}  tokens={m['tokens']}")
            rows.append({
                "id": item["id"], "category": item["category"], "model": args.model,
                "temperature": args.temperature, "prompt": item["prompt"], **m,
            })
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_model = args.model.replace(":", "-").replace("/", "-")
    name = f"{safe_model}_t{args.temperature}_{args.tag + '_' if args.tag else ''}{stamp}.csv"
    path = os.path.join(args.output_dir, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Resultados guardados en {path}")


if __name__ == "__main__":
    main()
