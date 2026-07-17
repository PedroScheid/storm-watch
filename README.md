# StormWatch 🌧️

> Não mostramos se vai chover hoje. **Avisamos quando a chuva está vindo até você.**

StormWatch é um app de **prevenção**, não de clima. Ele avisa o usuário poucos minutos
antes da chuva chegar ao local monitorado, com estimativa de tempo de chegada (ETA), para
evitar prejuízos do dia a dia: recolher roupas do varal, proteger o carro contra granizo,
fechar janelas, guardar ferramentas ou se preparar para sair.

## Como funciona

1. O usuário abre o PWA e concede a localização.
2. Escolhe o local a monitorar (ou usa a localização atual).
3. O servidor guarda apenas as coordenadas, o token de notificação e a preferência de intensidade.
4. Um worker processa imagens de satélite periodicamente (GOES-19 / NOAA).
5. Se uma área de chuva estiver se aproximando do local, o servidor envia uma notificação push.

Exemplos de alerta:

```
🌧️ Chuva moderada em cerca de 30 minutos.
⛈️ Chuva forte se aproximando. ETA: 15 minutos.
⛈️ Possível granizo. Proteja veículos e objetos expostos.
```

## Arquitetura

```
┌────────────────────┐        HTTPS        ┌───────────────────────────┐
│  Frontend (PWA)    │  ───────────────▶   │  Backend (FastAPI)        │
│  React + TS        │   /locations        │  ┌─────────────────────┐  │
│  Leaflet + OSM     │   /subscribe        │  │ API REST            │  │
│  Service Worker    │ ◀───────────────    │  │ SQLite              │  │
│  Web Push          │   Web Push (VAPID)  │  └─────────────────────┘  │
└────────────────────┘                     │  ┌─────────────────────┐  │
  Cloudflare Pages                          │  │ Worker periódico    │  │
                                            │  │  GOES fetcher (S3)  │  │
                                            │  │  Processor (OpenCV) │  │
                                            │  │  Nowcast + ETA      │  │
                                            │  └─────────────────────┘  │
                                            └───────────────────────────┘
                                                Render          ▲
                                                                │ S3 anônimo
                                                    ┌───────────┴───────────┐
                                                    │ noaa-goes19            │
                                                    │ ABI-L2-RRQPEF (mm/h)   │
                                                    └────────────────────────┘
```

## Dados de satélite

- **Satélite:** GOES-19 (GOES-East, operacional desde abr/2025) — cobre toda a América do Sul.
- **Produto:** `ABI-L2-RRQPEF` — Rainfall Rate / Quantitative Precipitation Estimate, Full Disk,
  2 km de resolução, atualizado a cada 10 minutos, em **mm/h**.
- **Fonte:** bucket público `noaa-goes19` na AWS (`us-east-1`), acesso anônimo, gratuito.

Detalhes das decisões técnicas em [`backend/app/goes/README.md`](backend/app/goes/README.md).

## Estrutura

```
storm-watch/
├── backend/           # FastAPI + worker + pipeline GOES
├── frontend/          # React + TS + PWA (Vite)
└── infra/             # Deploy Cloudflare Pages + Render
```

## Rodando localmente

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # gere as chaves VAPID (ver infra/DEPLOY.md)
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Deploy

Veja [`infra/DEPLOY.md`](infra/DEPLOY.md) para Cloudflare Pages (frontend), domínio/DNS e Render (backend).

## O que NÃO fazemos

Previsão para amanhã, temperatura, umidade, vento, gráficos complexos, contas de usuário.

## Privacidade

Armazenamos apenas: latitude/longitude do local monitorado, token de notificação e preferência
de intensidade. Nunca: nome, e-mail, senha, histórico de localização ou histórico de alertas.
