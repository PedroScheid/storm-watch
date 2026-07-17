# Cloudflare Pages — referência rápida

Build settings do projeto (frontend):

| Campo                   | Valor            |
|-------------------------|------------------|
| Framework preset        | None / Vite      |
| Root directory          | `frontend`       |
| Build command           | `npm run build`  |
| Build output directory  | `dist`           |
| Node version            | 20               |

Variáveis de ambiente (Production e Preview):

| Nome            | Valor                              |
|-----------------|------------------------------------|
| `VITE_API_URL`  | `https://api.stormwatch.app`       |

## SPA / PWA

O app é single-page. Se adicionar rotas client-side, crie `frontend/public/_redirects`:

```
/*  /index.html  200
```

O service worker (`public/sw.js`) e o `manifest.webmanifest` são servidos como
estáticos a partir da raiz — não precisam de configuração extra na Pages.

## Cabeçalhos (opcional)

Para garantir escopo do service worker e cache correto, `frontend/public/_headers`:

```
/sw.js
  Cache-Control: no-cache
  Service-Worker-Allowed: /
```
