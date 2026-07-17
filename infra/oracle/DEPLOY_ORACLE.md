# Deploy 24/7 grátis — Oracle Cloud Always Free + Cloudflare Tunnel

Backend (FastAPI + worker) numa VM sempre ligada da Oracle, exposto com HTTPS via
Cloudflare Tunnel. Frontend continua na Cloudflare Pages.

```
iPhone ─▶ https://<seu-app>.pages.dev      (Cloudflare Pages — frontend)
                     │  fetch
                     ▼
        https://api.SEUDOMINIO.com          (Cloudflare Tunnel — HTTPS grátis)
                     │
                     ▼
        cloudflared ─▶ 127.0.0.1:8000        (VM Oracle Always Free)
                     │  uvicorn + worker (systemd)
                     ▼
           bucket público noaa-goes19 (AWS)
```

> **Pré-requisito para HTTPS estável:** um domínio na sua conta Cloudflare (o túnel
> nomeado precisa de um hostname numa zona sua). Se quiser só testar já, sem domínio,
> veja a seção "Teste rápido sem domínio" no fim.

---

## 1. Criar a VM na Oracle

1. Crie conta em cloud.oracle.com (pede cartão para verificação, **não cobra** no
   Always Free).
2. **Compute → Instances → Create Instance.**
   - **Image:** Canonical Ubuntu 24.04
   - **Shape (preferida):** `VM.Standard.A1.Flex` (ARM Ampere), **1 OCPU / 6 GB**.
   - Se o A1.Flex **não aparecer na lista** (falta de capacidade ARM em São Paulo —
     comum), use a **`VM.Standard.E2.1.Micro`** (1 OCPU / 1 GB, também Always Free).
     O código lê só o recorte da imagem e o `setup.sh` cria 2 GB de swap, então roda
     bem em 1 GB. Se quiser o A1 depois, é só recriar quando houver capacidade.
   - **Add SSH keys:** gere/use uma chave SSH e **salve a chave privada**.
3. Crie e anote o **IP público**.

### Conectar por SSH (do seu Windows, PowerShell)

```powershell
ssh -i C:\caminho\da\sua-chave ubuntu@SEU_IP_PUBLICO
```

## 2. Clonar o projeto e instalar

Na VM:

```bash
git clone https://github.com/PedroScheid/storm-watch.git
cd storm-watch/backend
bash ../infra/oracle/setup.sh
```

O script instala tudo e imprime as chaves VAPID. Crie o `.env`:

```bash
cp .env.example .env
nano .env
```

Preencha:
- `VAPID_PUBLIC_KEY` e `VAPID_PRIVATE_KEY` (as que o script imprimiu);
- `CORS_ORIGINS=https://<seu-app>.pages.dev` (a URL do seu frontend);
- pode deixar o resto no padrão.

## 3. Rodar como serviço (systemd, sempre ligado)

```bash
sudo cp ../infra/oracle/stormwatch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now stormwatch
systemctl status stormwatch          # deve estar "active (running)"
curl http://127.0.0.1:8000/health    # -> {"status":"ok"}
```

Ver logs / worker em ação:

```bash
journalctl -u stormwatch -f
```

O serviço reinicia sozinho se cair ou se a VM reiniciar.

## 4. Expor com HTTPS via Cloudflare Tunnel

Instale o `cloudflared` (ARM64) na VM:

```bash
curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb
cloudflared --version
```

Autentique e crie o túnel (o `login` abre uma URL — cole no navegador e escolha seu
domínio):

```bash
cloudflared tunnel login
cloudflared tunnel create stormwatch      # anote o TUNNEL_ID que ele mostra
```

Crie a config do túnel:

```bash
nano ~/.cloudflared/config.yml
```

Use o modelo em `infra/oracle/cloudflared-config.example.yml`, trocando `TUNNEL_ID`
e `api.SEUDOMINIO.com`. Aponte o DNS e suba como serviço:

```bash
cloudflared tunnel route dns stormwatch api.SEUDOMINIO.com
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

Teste de qualquer lugar: `https://api.SEUDOMINIO.com/health` → `{"status":"ok"}`.

## 5. Ligar o frontend

Na Cloudflare Pages → seu projeto → **Settings → Environment variables**:

- `VITE_API_URL = https://api.SEUDOMINIO.com`

Refaça o deploy do frontend (Deployments → Retry/Redeploy). Confirme que o
`CORS_ORIGINS` no `.env` da VM tem a URL da Pages; se mudar, edite o `.env` e rode
`sudo systemctl restart stormwatch`.

## 6. Testar no iPhone

1. Abra a URL da Pages no **Safari** → Compartilhar (⬆️) → **"Adicionar à Tela de Início"**.
2. Abra o app pelo **ícone** (não pela aba do Safari).
3. Permita localização e toque em **"Ativar alertas de chuva"** → permita notificações.
4. Dispare um teste (de qualquer terminal):
   ```
   curl -X POST https://api.SEUDOMINIO.com/debug/test-push
   ```
   A notificação deve chegar no iPhone. Requer iOS 16.4+.

Agora o worker roda 24/7 na VM: a cada 5 min ele checa o GOES-19 e, se uma célula de
chuva estiver se aproximando do seu local, envia o alerta — mesmo com o app fechado.

---

## Atualizar o app depois

```bash
cd ~/storm-watch && git pull
cd backend && .venv/bin/pip install -r requirements.txt
sudo systemctl restart stormwatch
```

## Teste rápido sem domínio (URL temporária)

Se ainda não registrou o domínio e quer testar já, use um "quick tunnel" (URL
aleatória `*.trycloudflare.com`, muda a cada reinício — só para teste):

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Copie a URL `https://...trycloudflare.com` que ele mostrar, coloque em `VITE_API_URL`
(na Pages) e em `CORS_ORIGINS` (no `.env` da VM, depois `systemctl restart stormwatch`).

## Manutenção / observações

- A Oracle pode recuperar VMs Always Free **ociosas**; a nossa não fica ociosa (worker
  ativo), mas mantenha a conta ativa.
- Banco em `backend/data/stormwatch.db` (persistente no disco da VM).
- Segurança: o uvicorn escuta só em `127.0.0.1`; o acesso externo passa só pelo túnel
  Cloudflare (não precisa abrir portas no firewall da Oracle).
