# k8s_deploy_portforward_cleanup

Poenostavljen lokalni deploy za Docker Desktop Kubernetes.

Kaj naredi:
- (opcijsko) pobriše namespace `reactor-monitor`
- apply-a `infra/k8s/*.yaml` v pravem vrstnem redu
- počaka, da so podi Ready
- avtomatsko zažene port-forward za:
  - sensor-manager
  - archiver
  - controller
- pritisneš `q` -> ustavi port-forward + pobriše namespace (torej “ugasne vse”)

## Predpogoji
- Docker Desktop: Enable Kubernetes
- `kubectl` v PATH (context: `docker-desktop`)
- Python 3

Hitri check:
```bat
kubectl config use-context docker-desktop
kubectl get nodes
```

## Uporaba (copy/paste)

### Reset + deploy + port-forward
```bat
python tools\k8s_deploy_portforward_cleanup\k8s_up.py --reset
```

Ko dela, ti izpiše URL-je (tipično):
- SensorManager: http://localhost:8081
- Archiver: http://localhost:8082
- Controller: http://localhost:8083

Pritisni `q` za stop + cleanup.

### Port-forward v ločenih oknih (Windows)
Če nočeš, da ti ta terminal ostane “zaseden”:
```bat
python tools\k8s_deploy_portforward_cleanup\k8s_up.py --reset --pf-windows
```

### Samo port-forward (če je že vse deployano)
```bat
python tools\k8s_deploy_portforward_cleanup\k8s_up.py --no-apply --no-wait
```

## Troubleshooting
- Če port-forward faila, preveri:
```bat
kubectl get pods -n reactor-monitor
kubectl get svc -n reactor-monitor
```
- Če se namespace ne pobriše takoj: `kubectl get ns` (K8s včasih rabi malo časa).
