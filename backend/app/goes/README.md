# Pipeline GOES — decisões técnicas

Este documento responde às perguntas do PRD sobre dados e algoritmo.

## Dados

**Qual banda/produto do GOES usar?**
Em vez de estimar chuva a partir de uma banda de infravermelho bruta (proxy por
temperatura do topo de nuvem), usamos o produto derivado **ABI-L2-RRQPEF**
(Rainfall Rate / Quantitative Precipitation Estimate, Full Disk). Ele já entrega a
**taxa de chuva instantânea em mm/h** na grade fixa do ABI (2 km), calculada pela
própria NOAA combinando canais IR. Isso reduz muito o esforço de calibração e os
falsos positivos de nuvens frias sem chuva (cirros).

- Satélite: **GOES-19** (GOES-East, operacional desde 04/2025), subsatélite em 75,2° W.
- Cobertura: Full Disk inclui toda a América do Sul.
- Bucket público: `noaa-goes19` (AWS `us-east-1`), acesso **anônimo**.
- Chave: `ABI-L2-RRQPEF/<ano>/<dia_do_ano>/<hora>/OR_...-M6_G19_s<timestamp>...nc`

**Qual intervalo de atualização (5, 10 ou 15 min)?**
O RRQPEF Full Disk sai a cada **~10 minutos**. Fazemos *polling* a cada **5 min**
(`POLL_INTERVAL_SECONDS`) para pegar o quadro novo com baixa latência, mas o
processamento é idempotente: se não há quadro novo, nada é reprocessado.

**Como lidar com indisponibilidade dos dados?**
O fetcher varre a hora atual e as **2 horas anteriores** ao listar chaves, o que
absorve viradas de hora e atrasos de publicação. Se o download/parse falhar, o
worker registra o erro e mantém o último estado — nenhum alerta falso é gerado por
ausência de dado. Alertas ativos só são cancelados quando um quadro **válido** deixa
de detectar a célula.

## Algoritmo

**Como detectar nuvens/áreas de chuva intensas?**
Limiarizamos a taxa de chuva (`RRQPE`) e rotulamos **componentes conexos**
(`cv2.connectedComponentsWithStats`). Cada componente vira uma "célula" com pico de
intensidade e centróide. Ruído (< ~12 km²) é descartado.

Faixas de intensidade (mm/h, ajustáveis no `.env`):

| Nível        | Limiar (mm/h) |
|--------------|---------------|
| moderada     | ≥ 2,5         |
| forte        | ≥ 10          |
| muito forte  | ≥ 50          |

**Como calcular direção e velocidade?**
**Fluxo óptico denso** (Farneback, OpenCV) entre os dois últimos quadros. A média
do campo de deslocamento, ponderada pelos pixels com chuva, dá o vetor de movimento
em pixels/quadro. Convertendo por 2 km/pixel e pelo intervalo real entre quadros
(derivado dos *timestamps*), obtemos velocidade em km/h e direção.

**Como estimar o ETA?**
Projetamos o vetor de movimento sobre a direção célula→alvo (produto escalar). O
componente que "fecha" a distância é a velocidade de aproximação. O ETA é a distância
até a **borda do raio de alerta** dividida por essa velocidade de aproximação.

**Como reduzir falsos positivos?**
- Produto RRQPE já filtra nuvem fria sem chuva.
- Só alertamos para células **se aproximando** (velocidade de aproximação > 0).
- Área mínima de célula descarta pixels isolados.
- Dedup por setor de rumo (30°) + faixa de distância (20 km) evita alerta repetido.

## Backend / cache

**Como evitar reprocessar as mesmas imagens?**
O worker guarda a chave S3 do último quadro processado por posição; se a chave não
mudou, pula. (Ver `app/worker.py`.)

**Estratégia de cache?**
Os quadros recortados são pequenos (janela de ~120 km) e ficam em memória no ciclo
do worker. Não persistimos NetCDF em disco por padrão (`backend/data/` é ignorado no
git e serve só para depuração).

**Como monitorar erros do processamento?**
Cada ciclo loga sucesso/falha por posição via `logging`. Em produção (Render), os
logs ficam disponíveis no painel; um contador de falhas consecutivas pode disparar
alerta operacional.
