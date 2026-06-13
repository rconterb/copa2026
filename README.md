# 🏆 Copa 2026 — Calendário Dinâmico (ICS)

Serviço que gera um calendário `.ics` da Copa do Mundo 2026 para você **assinar no
Google Calendar**. Diferente de um arquivo importado uma vez, o calendário assinado
**atualiza sozinho**: o Google revisita a URL a cada 8–24h e busca os dados mais
recentes — placares dos jogos já disputados e os confrontos do mata-mata conforme
vão sendo definidos.

- **Horários em Brasília** (conversão automática do fuso de cada sede).
- **Lembretes:** jogos do **Brasil** avisam **1 dia, 2h e 1h** antes; **seleções principais**
  (França, Espanha, Argentina, Inglaterra, Portugal, Alemanha, Holanda) avisam **2h e 1h** antes.
- **Fonte de dados:** [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) — pública, domínio público, sem chave de API.

## Endpoints

| Rota | O que é |
|------|---------|
| `/` | Página com as URLs e instruções |
| `/copa2026.ics` | Calendário completo (104 jogos) |
| `/brasil.ics` | Só os jogos do Brasil |
| `/health` | Healthcheck (usado pelo Railway) |

## Deploy no Railway (5 minutos)

1. Suba estes arquivos num repositório no GitHub (ou use `railway up` pela CLI).
2. No Railway: **New Project → Deploy from GitHub repo** (ou **Empty → Deploy**).
3. O Railway detecta Python via Nixpacks e instala o `requirements.txt` sozinho.
4. Em **Settings → Networking**, clique em **Generate Domain** para ter uma URL pública.
5. Pronto. Sua URL será algo como `https://copa-cal-production.up.railway.app`.

Não há variáveis de ambiente obrigatórias. O serviço já funciona assim que sobe.

### Rodar local (opcional, para testar)

```bash
pip install -r requirements.txt
uvicorn main:app --reload
# abra http://localhost:8000
```

## Como assinar no Google Calendar (atualiza sozinho)

> Importante: para o calendário **atualizar sozinho**, use **"De URL"** (assinar),
> NÃO use "Importar". Importar copia uma vez; assinar mantém sincronizado.

1. Abra o **Google Calendar no computador** (não dá pra assinar URL pelo app do celular,
   mas depois de assinar ele aparece no celular também).
2. Menu lateral esquerdo → **Outras agendas** → botão **+** → **De URL**.
3. Cole a URL do calendário, por exemplo:
   `https://SEU-DOMINIO.up.railway.app/copa2026.ics`
   (ou `/brasil.ics` para só o Brasil).
4. Clique em **Adicionar agenda**.
5. Os jogos aparecem em poucos minutos e passam a atualizar automaticamente.

## Como funciona o "dinâmico"

- O Google **não** atualiza em tempo real (não é ao vivo). Ele revisita a URL a cada
  algumas horas. Por isso os placares aparecem com algum atraso, e os confrontos do
  mata-mata surgem quando a fonte de dados os publica.
- Cada jogo tem um **UID estável**, então quando o placar muda ou um confronto é
  definido, o evento **atualiza no lugar** em vez de duplicar.
- Se a fonte de dados ficar fora do ar, o serviço devolve o último estado em cache.

## Notas técnicas

- O `.ics` segue o RFC 5545 (validado com a lib `icalendar`).
- Fuso de Brasília fixo em UTC−3 (sem horário de verão desde 2019), declarado no
  bloco `VTIMEZONE`.
- Cache em memória de 30 min para não sobrecarregar a fonte.
- A duração de cada evento é estimada em 2h (jogo + intervalo).
