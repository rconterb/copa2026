# 🏆 Copa 2026 — App Consolidado (Grupos + Chaveamento + Calendário)

Um app só, servido no Railway, com tudo num link:

- **📋 Grupos** — os 12 grupos editáveis (arraste/toque para mudar 1º/2º/3º/4º) e a escolha dos 8 melhores terceiros.
- **🏆 Chaveamento** — bracket interativo estilo ESPN (final ao centro, linhas conectoras). Toque em quem vence e a chave se monta; muda os grupos e o chaveamento se refaz sozinho. Brasil em destaque.
- **📅 Calendário** — lista de todos os jogos por dia, com **horário de Brasília**, placares (quando jogados) e botões para **assinar no Google Calendar** (atualiza sozinho) ou **baixar o .ics**.

Os horários e placares vêm da fonte pública openfootball/worldcup.json (domínio público, sem chave de API).

## Rotas

| Rota | O que é |
|------|---------|
| `/` | O app consolidado (Grupos + Chaveamento + Calendário) |
| `/bracket`, `/app` | Atalhos para o mesmo app |
| `/copa2026.ics` | Calendário completo para assinar/importar |
| `/brasil.ics` | Só os jogos do Brasil |
| `/jogos.json` | Jogos em JSON (usado pela aba Calendário) |
| `/info` | Página antiga só com as URLs dos calendários |
| `/health` | Healthcheck (Railway) |

## Arquivos

    main.py            servidor FastAPI (rotas + .ics + jogos.json)
    bracket.html       o app consolidado (3 abas)
    requirements.txt   dependencias
    Procfile           comando de start
    railway.json       config do Railway
    README.md          este arquivo

## Deploy no Railway

1. Atualize os arquivos no repositorio GitHub.
2. O Railway detecta o commit e faz redeploy automatico (1-2 min).
3. O app fica em https://SEU-DOMINIO.up.railway.app/

## Como usar

- Mande o LINK https://SEU-DOMINIO.up.railway.app/ para qualquer pessoa.
  Por ser uma URL (nao um arquivo), abre no navegador de qualquer celular e o
  JavaScript roda sempre - sem o problema de "parece uma imagem" que acontece
  ao abrir um .html solto no iPhone.
- Na aba Calendario: "Assinar no Google" (atualiza sozinho) ou "Baixar .ics".

## Lembretes do calendario

- Brasil: 1 dia, 2h e 1h antes.
- Selecoes principais (Franca, Espanha, Argentina, Inglaterra, Portugal,
  Alemanha, Holanda): 2h e 1h antes.

## Notas

- O calendario assinado nao e ao vivo: o Google revisita a URL a cada 8-24h.
- Datas/sedes do mata-mata sao oficiais; horarios exatos de cada confronto se
  confirmam conforme a FIFA define os classificados.
- O .ics segue o RFC 5545; fuso de Brasilia fixo em UTC-3.
