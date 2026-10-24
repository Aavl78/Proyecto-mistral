"""Resume las corridas (promedio y desviacion estandar) y genera graficos.

Uso: python src/analizar.py
Lee   results/*_<config>_run<N>_*.csv  y  results/monitor.csv
Crea  results/resumen.csv  y  docs/fig_*.png
"""
import csv
import glob
import os
import re
import statistics
from collections import defaultdict

RESULTS = "results"
DOCS = "docs"
PATRON = re.compile(r"_(?P<cfg>[a-z0-9]+)_run(?P<run>\d+)_\d{8}_\d{6}\.csv$")


def media_desv(valores):
    """Promedio y desviacion estandar muestral (n-1)."""
    d = statistics.stdev(valores) if len(valores) > 1 else 0.0
    return statistics.mean(valores), d


def leer_corridas():
    """Devuelve {config: {run: {'ttft': prom, 'tps': prom}}} (promedio sobre los prompts)."""
    datos = defaultdict(dict)
    for ruta in glob.glob(os.path.join(RESULTS, "*.csv")):
        m = PATRON.search(os.path.basename(ruta))
        if not m:
            continue
        with open(ruta, newline="", encoding="utf-8-sig") as f:
            filas = list(csv.DictReader(f))
        datos[m["cfg"]][int(m["run"])] = {
            "ttft": statistics.mean(float(x["ttft_s"]) for x in filas),
            "tps": statistics.mean(float(x["tokens_per_s"]) for x in filas),
        }
    return datos


def leer_monitor():
    """Devuelve {config: {'ram': [..], 'cpu': [..]}} desde monitor.csv."""
    ruta = os.path.join(RESULTS, "monitor.csv")
    datos = defaultdict(lambda: {"ram": [], "cpu": []})
    if not os.path.exists(ruta):
        return datos
    with open(ruta, newline="", encoding="ascii") as f:
        for x in csv.DictReader(f):
            datos[x["config"]]["ram"].append(float(x["peak_ram_gb"]))
            datos[x["config"]]["cpu"].append(float(x["avg_cpu_pct"]))
    return datos


def main():
    corridas = leer_corridas()
    if not corridas:
        raise SystemExit("No hay corridas en results/ con etiqueta <config>_run<N>.")
    monitor = leer_monitor()

    metricas = {  # clave: (etiqueta del eje, {config: [valores por corrida]})
        "ttft": ("Tiempo al primer token (s)", {}),
        "tps": ("Velocidad de generación (tokens/s)", {}),
        "ram": ("Memoria pico (GB)", {}),
        "cpu": ("Uso medio de CPU (%)", {}),
    }
    for cfg, runs in corridas.items():
        metricas["ttft"][1][cfg] = [r["ttft"] for r in runs.values()]
        metricas["tps"][1][cfg] = [r["tps"] for r in runs.values()]
        if cfg in monitor:
            metricas["ram"][1][cfg] = monitor[cfg]["ram"]
            metricas["cpu"][1][cfg] = monitor[cfg]["cpu"]

    os.makedirs(DOCS, exist_ok=True)
    filas = []
    for clave, (etiqueta, porcfg) in metricas.items():
        for cfg, vals in sorted(porcfg.items()):
            m, d = media_desv(vals)
            filas.append({"metrica": etiqueta, "config": cfg, "promedio": round(m, 3),
                          "desviacion": round(d, 3), "n_corridas": len(vals)})
            print(f"{etiqueta:38s} {cfg:8s} {m:8.2f} +/- {d:.2f} (n={len(vals)})")

    with open(os.path.join(RESULTS, "resumen.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["metrica", "config", "promedio", "desviacion", "n_corridas"])
        w.writeheader()
        w.writerows(filas)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib no esta instalado: se omiten los graficos (resumen.csv si se genero).")
        return

    for clave, (etiqueta, porcfg) in metricas.items():
        if not porcfg:
            continue
        cfgs = sorted(porcfg)
        medias = [media_desv(porcfg[c])[0] for c in cfgs]
        desvs = [media_desv(porcfg[c])[1] for c in cfgs]
        fig, ax = plt.subplots(figsize=(5, 3.5))
        nombres = [{"native": "Nativo", "docker": "Docker"}.get(c, c) for c in cfgs]
        ax.bar(nombres, medias, yerr=desvs, capsize=6, color=["#4c72b0", "#dd8452", "#55a868"][:len(cfgs)])
        ax.set_ylabel(etiqueta)
        ax.set_xlabel("Configuración")
        fig.tight_layout()
        destino = os.path.join(DOCS, f"fig_{clave}.png")
        fig.savefig(destino, dpi=200)
        plt.close(fig)
        print(f"Grafico: {destino}")


if __name__ == "__main__":
    main()
