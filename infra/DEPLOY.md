# Deploy do StormWatch

Frontend (PWA) na **Cloudflare Pages**, backend (FastAPI + worker) no **Render**,
domínio gerenciado na **Cloudflare**.

```
Usuário ── https://stormwatch.app ──▶ Cloudflare Pages (frontend)
                                          │  fetch /api…
                                          ▼
                          https://api.stormwatch.app ──▶ Render (FastAPI)
                                          │
                                          ▼
                             bucket público noaa-goes19 (AWS)
```

## 0. Pré-requisitos

- Conta na Cloudflare e na Render.
- Repositório no GitHub (Cloudflare Pages e Render fazem deploy a partir dele).

## 1. Gerar as chaves VAPID (Web Push)

No backend, com as dependências instaladas:

```bash
cd backend
python - <<'PY'
from py_vapid import Vapid02
import base64
v = Vapid02()
v.generate_keys()
def b64(pem): return base64.urlsafe_b64encode(pem).decode().strip("=")
print("VAPID_PUBLIC_KEY =", v.public_key_urlsafe_base64())
print("VAPID_PRIVATE_KEY=", b64(v.private_pem()))
PY
```

Guarde as duas chaves. A **pública** vai para o frontend (via API) e o backend; a
**privada** fica só no backend (variável secreta na Render).

> Alternativa rápida: `npx web-push generate-vapid-keys`.

## 2. Registrar o domínio na Cloudflare

1. Cloudflare Dashboard → **Domain Registration → Register Domain**.
2. Escolha o domínio (ex.: `stormwatch.app`) e finalize a compra.
   - Já vem com DNS na Cloudflare, sem necessidade de trocar nameservers.
3. Depois de registrado, ele aparece em **Websites** com a zona DNS pronta.

## 3. Backend no Render

1. Render → **New → Blueprint** e aponte para `infra/render.yaml` (rootDir `backend`).
2. Em **Environment**, defina os secretos:
   - `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` (passo 1).
3. Deploy. Anote a URL pública (ex.: `https://stormwatch-api.onrender.com`).
4. Teste: `curl https://stormwatch-api.onrender.com/health` → `{"status":"ok"}`.

> **Nota sobre o worker:** ele roda dentro do processo FastAPI (evento de lifespan),
> então o serviço não pode "dormir". No plano free a Render suspende após
> inatividade — use pelo menos o plano **Starter** para os alertas rodarem 24/7.

### Subdomínio api.stormwatch.app (opcional, recomendado)

Na Render → serviço → **Settings → Custom Domains** → adicione `api.stormwatch.app`.
A Render dá um alvo CNAME; crie na Cloudflare (passo 5) um registro CNAME
`api` → alvo da Render, **DNS only** (nuvem cinza) para o TLS da Render funcionar.

## 4. Frontend na Cloudflare Pages

1. Cloudflare → **Workers & Pages → Create → Pages → Connect to Git**.
2. Selecione o repositório. Configuração de build:
   - **Root directory:** `frontend`
   - **Build command:** `npm run build`
   - **Build output directory:** `dist`
3. **Environment variables** (Production):
   - `VITE_API_URL = https://api.stormwatch.app` (ou a URL `.onrender.com`)
4. Deploy. Sai algo como `https://stormwatch.pages.dev`.

## 5. Ligar o domínio ao frontend

1. Na Pages → projeto → **Custom domains → Set up a domain** → `stormwatch.app`
   (e `www.stormwatch.app`). Como o domínio já está na Cloudflare, os registros
   são criados automaticamente.
2. Atualize o CORS do backend (`CORS_ORIGINS`) para incluir
   `https://stormwatch.app` e redeploy.

## 6. Checklist final

- [ ] `GET /health` responde `ok` na URL da Render.
- [ ] `GET /vapid-public-key` retorna a chave pública.
- [ ] Frontend carrega em `https://stormwatch.app` e o service worker registra
      (DevTools → Application → Service Workers).
- [ ] "Ativar alertas" pede permissão e cria a subscription sem erro de CORS.
- [ ] `GET /nowcast?lat=-25.42&lon=-49.27` retorna células (com chuva na região).

## Notas de HTTPS / PWA

Web Push e Service Workers exigem **HTTPS** (Cloudflare Pages e Render já fornecem).
No iPhone, o push só funciona com o app **instalado na tela inicial** (iOS 16.4+); a
UI já orienta o usuário (componente `InstallHint`).
