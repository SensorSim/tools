# hpa_scaling_demo

Majhen script za demo “HPA scaling” 

Ideja:
- sproži load (CPU) na `controller` (ali drug deployment)
- sproti izpisuje HPA stanje + št. replik
- ti narediš screenshot/izpis kot dokaz, da se replike povečajo

## Predpogoji
- Sistem mora že teči na K8s (npr. z `k8s_up.py`)
- HPA mora obstajati (npr. `controller-hpa`)

Check:
```bat
kubectl get hpa -n reactor-monitor
kubectl get pods -n reactor-monitor
```

## Uporaba (copy/paste)

### 1) Najbolj zanesljivo: CPU burn v podu (mode exec)
```bat
python tools\hpa_scaling_demo\hpa_demo.py --mode exec --duration 90 --deploy controller --hpa controller-hpa
```

### 2) Alternativa: HTTP spam (mode http)
Uporabi, če imaš dober endpoint in hočeš “real traffic”.
```bat
python tools\hpa_scaling_demo\hpa_demo.py --mode http --duration 90 --url http://localhost:8083/health/live --concurrency 80 --deploy controller --hpa controller-hpa
```

## Dokaz
- output skripte (replicas before/after + HPA line)
- ali v drugem terminalu:
```bat
kubectl get hpa -n reactor-monitor -w
kubectl get pods -n reactor-monitor -w
```

## Če HPA kaže <unknown>
Če v `kubectl get hpa` vidiš `unknown`, potem metrics niso na voljo (metrics-server).
Brez tega HPA ne bo skaliral po CPU.
