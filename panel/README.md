# Panel visual QKD

Aplicacion local para explorar simulaciones QKD con una API FastAPI y una web
Vite/React.

## Arranque de desarrollo

Desde la raiz del repositorio:

```powershell
..\.venv\Scripts\python.exe -m uvicorn panel.api.app:create_app --factory --reload --host 127.0.0.1 --port 8000
```

En otra terminal:

```powershell
cd panel\web
npm.cmd install
npm.cmd run dev
```

La web queda disponible en `http://127.0.0.1:5173` y usa el proxy de Vite para
leer la API en `/api`.

## Verificacion rapida

```powershell
..\.venv\Scripts\python.exe -m pytest tests\panel_api -q
cd panel\web
npm.cmd test
npm.cmd run lint
npm.cmd run build
```
