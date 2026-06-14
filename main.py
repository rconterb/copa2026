"""
Copa 2026 — Calendário dinâmico (ICS) para Google Calendar.

Como funciona
--------------
Este serviço expõe uma URL .ics que o Google Calendar pode ASSINAR.
O Google revisita a URL periodicamente (a cada 8-24h) e atualiza os eventos
sozinho. A cada visita, buscamos os dados mais recentes dos jogos da Copa
(fonte pública openfootball, sem chave de API), convertemos para horário de
Brasília e devolvemos o .ics atualizado — com placares quando os jogos já
foram disputados e com os confrontos do mata-mata conforme vão sendo definidos.

Endpoints
---------
GET /                -> página simples com instruções
GET /copa2026.ics    -> calendário completo (todos os jogos)
GET /brasil.ics      -> só os jogos do Brasil
GET /health          -> healthcheck p/ o Railway
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import time
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Response, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse, JSONResponse
from pathlib import Path

BASE_DIR = Path(__file__).parent

# Onde guardar os palpites. No Railway, se houver um Volume montado em /data,
# usa ele (persiste entre deploys). Senão, usa um arquivo local.
STORE_DIR = Path("/data") if Path("/data").is_dir() else BASE_DIR
PALPITES_FILE = STORE_DIR / "palpites.json"

# ----------------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------------
DATA_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
TZ_BR = ZoneInfo("America/Sao_Paulo")
CACHE_TTL = 60 * 30  # 30 min: evita bater na fonte a cada request
DEFAULT_DURATION_MIN = 120  # duração estimada de cada jogo (com intervalo)

# seleções "principais" (favoritas ao título) — ganham lembretes 2h e 1h antes.
# O Brasil tem tratamento especial (1 dia, 2h e 1h antes).
SELECOES_PRINCIPAIS = {
    "França", "Espanha", "Argentina", "Inglaterra",
    "Portugal", "Alemanha", "Holanda",
}

# tradução de nomes de seleção (inglês -> português) para os jogos
TEAM_PT = {
    "Mexico": "México", "South Africa": "África do Sul", "South Korea": "Coreia do Sul",
    "Czech Republic": "Rep. Tcheca", "Canada": "Canadá", "Bosnia and Herzegovina": "Bósnia",
    "Qatar": "Catar", "Switzerland": "Suíça", "Brazil": "Brasil", "Morocco": "Marrocos",
    "Haiti": "Haiti", "Scotland": "Escócia", "United States": "EUA", "Paraguay": "Paraguai",
    "Australia": "Austrália", "Turkey": "Turquia", "Türkiye": "Turquia", "Germany": "Alemanha",
    "Curacao": "Curaçao", "Curaçao": "Curaçao", "Ivory Coast": "Costa do Marfim",
    "Cote d'Ivoire": "Costa do Marfim", "Ecuador": "Equador", "Netherlands": "Holanda",
    "Japan": "Japão", "Sweden": "Suécia", "Tunisia": "Tunísia", "Belgium": "Bélgica",
    "Egypt": "Egito", "Iran": "Irã", "New Zealand": "Nova Zelândia", "Spain": "Espanha",
    "Cape Verde": "Cabo Verde", "Cabo Verde": "Cabo Verde", "Saudi Arabia": "Arábia Saudita",
    "Uruguay": "Uruguai", "France": "França", "Senegal": "Senegal", "Iraq": "Iraque",
    "Norway": "Noruega", "Argentina": "Argentina", "Algeria": "Argélia", "Austria": "Áustria",
    "Jordan": "Jordânia", "Portugal": "Portugal", "DR Congo": "RD Congo",
    "Congo DR": "RD Congo", "Uzbekistan": "Uzbequistão", "Colombia": "Colômbia",
    "England": "Inglaterra", "Croatia": "Croácia", "Ghana": "Gana", "Panama": "Panamá",
}

# tradução das fases (round) para português
ROUND_PT = {
    "Round of 32": "Rodada de 32", "Round of 16": "Oitavas de Final",
    "Quarter-finals": "Quartas de Final", "Quarter-final": "Quartas de Final",
    "Semi-finals": "Semifinal", "Semi-final": "Semifinal",
    "Match for third place": "Disputa 3º Lugar", "Third place": "Disputa 3º Lugar",
    "Final": "Final",
}

app = FastAPI(title="Copa 2026 — Calendário Dinâmico")

# cache simples em memória
_cache: dict[str, Any] = {"ts": 0.0, "data": None}


# ----------------------------------------------------------------------------
# Busca de dados (com cache)
# ----------------------------------------------------------------------------
def fetch_matches() -> list[dict]:
    now = time.time()
    if _cache["data"] is not None and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]
    try:
        r = httpx.get(DATA_URL, timeout=15.0, follow_redirects=True)
        r.raise_for_status()
        matches = r.json().get("matches", [])
        _cache["data"] = matches
        _cache["ts"] = now
        return matches
    except Exception:
        # se a fonte cair, devolve o último cache (mesmo velho) ou vazio
        return _cache["data"] or []


# ----------------------------------------------------------------------------
# Conversão de horário -> Brasília
# ----------------------------------------------------------------------------
def parse_kickoff(date_str: str, time_str: str) -> dt.datetime | None:
    """
    date_str: '2026-06-13'
    time_str: '19:00 UTC-6' (pode vir sem o UTC)
    Retorna datetime em Brasília.
    """
    if not date_str:
        return None
    m = re.match(r"(\d{1,2}):(\d{2})", time_str or "")
    hh, mm = (int(m.group(1)), int(m.group(2))) if m else (12, 0)
    # offset do fuso de origem
    off = re.search(r"UTC([+-]\d{1,2})", time_str or "")
    src_off = int(off.group(1)) if off else -4  # padrão Costa Leste EUA
    try:
        y, mo, d = map(int, date_str.split("-"))
    except ValueError:
        return None
    src_tz = dt.timezone(dt.timedelta(hours=src_off))
    naive = dt.datetime(y, mo, d, hh, mm, tzinfo=src_tz)
    return naive.astimezone(TZ_BR)


def team_pt(name: str) -> str:
    if not name:
        return name
    return TEAM_PT.get(name.strip(), name.strip())


def round_pt(name: str) -> str:
    return ROUND_PT.get((name or "").strip(), name or "")


# ----------------------------------------------------------------------------
# Geração do ICS
# ----------------------------------------------------------------------------
def ics_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", r"\;")
            .replace(",", r"\,").replace("\n", r"\n"))


def fold(line: str) -> str:
    """Dobra linhas em 75 octetos (regra do RFC 5545)."""
    out, cur = [], line
    while len(cur.encode("utf-8")) > 75:
        # corta em ~73 chars p/ segurança com UTF-8
        cut = 73
        out.append(cur[:cut])
        cur = " " + cur[cut:]
    out.append(cur)
    return "\r\n".join(out)


def build_ics(matches: list[dict], only_brazil: bool = False) -> str:
    now_utc = dt.datetime.now(dt.timezone.utc)
    dtstamp = now_utc.strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Copa2026//Calendario Dinamico//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{'Brasil na Copa 2026' if only_brazil else 'Copa do Mundo 2026'}",
        "X-WR-TIMEZONE:America/Sao_Paulo",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
        # VTIMEZONE de Brasília (sem horário de verão desde 2019)
        "BEGIN:VTIMEZONE",
        "TZID:America/Sao_Paulo",
        "BEGIN:STANDARD",
        "DTSTART:20191117T000000",
        "TZOFFSETFROM:-0300",
        "TZOFFSETTO:-0300",
        "TZNAME:-03",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

    for mt in matches:
        t1 = team_pt(mt.get("team1", ""))
        t2 = team_pt(mt.get("team2", ""))
        if only_brazil and "Brasil" not in (t1, t2):
            continue

        start = parse_kickoff(mt.get("date", ""), mt.get("time", ""))
        if start is None:
            continue
        end = start + dt.timedelta(minutes=DEFAULT_DURATION_MIN)

        rnd = round_pt(mt.get("round", ""))
        grp = mt.get("group", "")
        phase = grp or rnd  # grupo na 1a fase, fase no mata-mata
        ground = mt.get("ground", "")

        # placar dinâmico: se já houve jogo, mostra no título
        score = mt.get("score") or {}
        ft = score.get("ft")
        if ft and len(ft) == 2:
            title = f"⚽ {t1} {ft[0]} x {ft[1]} {t2}"
        else:
            title = f"⚽ {t1} x {t2}"

        # UID estável por confronto (mesmo evento atualiza, não duplica)
        raw_uid = f"{mt.get('date','')}-{mt.get('team1','')}-{mt.get('team2','')}-{phase}"
        uid = hashlib.md5(raw_uid.encode("utf-8")).hexdigest() + "@copa2026"

        desc_parts = []
        if phase:
            desc_parts.append(f"Fase: {phase}")
        if rnd and grp:
            desc_parts.append(rnd)
        if ground:
            desc_parts.append(f"Local: {ground}")
        desc_parts.append("Horário de Brasília")
        description = " — ".join(desc_parts)

        loc = ground
        is_br = "Brasil" in (t1, t2)
        is_principal = bool(SELECOES_PRINCIPAIS & {t1, t2})

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            fold(f"SUMMARY:{ics_escape(title)}"),
            f"DTSTART;TZID=America/Sao_Paulo:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND;TZID=America/Sao_Paulo:{end.strftime('%Y%m%dT%H%M%S')}",
            fold(f"DESCRIPTION:{ics_escape(description)}"),
            fold(f"LOCATION:{ics_escape(loc)}"),
            f"CATEGORIES:{'BRASIL' if is_br else 'COPA2026'}",
        ]

        # lembretes (VALARM). Brasil: 1 dia, 2h e 1h antes.
        # Seleções principais: 2h e 1h antes.
        def alarm(trigger: str, msg: str) -> list[str]:
            return ["BEGIN:VALARM", "ACTION:DISPLAY",
                    f"DESCRIPTION:{ics_escape(msg)}",
                    f"TRIGGER:-{trigger}", "END:VALARM"]

        if is_br:
            lines += alarm("P1D", "Amanhã tem Brasil na Copa! ⚽🇧🇷")
            lines += alarm("PT2H", "Brasil joga em 2 horas ⚽🇧🇷")
            lines += alarm("PT1H", "Brasil joga em 1 hora ⚽🇧🇷")
        elif is_principal:
            lines += alarm("PT2H", f"{t1} x {t2} em 2 horas ⚽")
            lines += alarm("PT1H", f"{t1} x {t2} em 1 hora ⚽")

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) if l.startswith(("SUMMARY", "DESC", "LOCATION")) is False else l
                       for l in lines) + "\r\n"


# ----------------------------------------------------------------------------
# Rotas
# ----------------------------------------------------------------------------
@app.get("/copa2026.ics")
def calendario_completo():
    ics = build_ics(fetch_matches(), only_brazil=False)
    return Response(content=ics, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": "inline; filename=copa2026.ics"})


@app.get("/brasil.ics")
def calendario_brasil():
    ics = build_ics(fetch_matches(), only_brazil=True)
    return Response(content=ics, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": "inline; filename=brasil.ics"})


@app.get("/jogos.json")
def jogos_json():
    """Jogos em JSON simples (português, horário de Brasília) para a aba Calendário."""
    out = []
    for mt in fetch_matches():
        start = parse_kickoff(mt.get("date", ""), mt.get("time", ""))
        if start is None:
            continue
        score = mt.get("score") or {}
        ft = score.get("ft")
        placar = f"{ft[0]} x {ft[1]}" if ft and len(ft) == 2 else None
        rnd = round_pt(mt.get("round", ""))
        grp = mt.get("group", "")
        out.append({
            "dia": start.strftime("%Y-%m-%d"),
            "hora": start.strftime("%Hh%M").replace("h00", "h"),
            "t1": team_pt(mt.get("team1", "")),
            "t2": team_pt(mt.get("team2", "")),
            "placar": placar,
            "fase": grp or rnd,
            "local": mt.get("ground", ""),
            "ts": start.isoformat(),
        })
    out.sort(key=lambda x: x["ts"])
    return {"matches": out}


@app.get("/health")
def health():
    return {"ok": True, "matches_cached": len(_cache["data"] or [])}


# ----------------------------------------------------------------------------
# Palpites por e-mail (identificação simples, sem senha — bolão entre amigos)
# ----------------------------------------------------------------------------
def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""))


def _load_all() -> dict:
    try:
        if PALPITES_FILE.exists():
            return json.loads(PALPITES_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_all(data: dict) -> bool:
    try:
        tmp = PALPITES_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, PALPITES_FILE)
        return True
    except Exception:
        return False


@app.get("/palpite")
def carregar_palpite(email: str = ""):
    """Carrega os palpites salvos de um e-mail. Sem e-mail válido, devolve vazio."""
    e = _norm_email(email)
    if not _valid_email(e):
        return JSONResponse({"ok": False, "erro": "email_invalido"}, status_code=400)
    data = _load_all()
    rec = data.get(e)
    if not rec:
        return {"ok": True, "encontrado": False, "palpite": None}
    return {"ok": True, "encontrado": True, "palpite": rec.get("palpite"),
            "atualizado": rec.get("atualizado")}


@app.post("/palpite")
async def salvar_palpite(req: Request):
    """Salva os palpites de um e-mail. Corpo JSON: {email, palpite}."""
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "erro": "json_invalido"}, status_code=400)
    e = _norm_email(body.get("email", ""))
    palpite = body.get("palpite")
    if not _valid_email(e):
        return JSONResponse({"ok": False, "erro": "email_invalido"}, status_code=400)
    if not isinstance(palpite, dict):
        return JSONResponse({"ok": False, "erro": "palpite_invalido"}, status_code=400)
    # limite de tamanho simples (anti-abuso)
    if len(json.dumps(palpite)) > 20000:
        return JSONResponse({"ok": False, "erro": "palpite_grande"}, status_code=413)
    data = _load_all()
    data[e] = {"palpite": palpite,
               "atualizado": dt.datetime.now(dt.timezone.utc).isoformat()}
    if not _save_all(data):
        return JSONResponse({"ok": False, "erro": "falha_ao_salvar"}, status_code=500)
    return {"ok": True}


def _serve_app():
    f = BASE_DIR / "bracket.html"
    if f.exists():
        return FileResponse(str(f), media_type="text/html; charset=utf-8")
    return HTMLResponse("<h1>bracket.html não encontrado no servidor</h1>", status_code=404)


@app.get("/", response_class=HTMLResponse)
def root():
    """App consolidado: Grupos + Chaveamento + Calendário."""
    return _serve_app()


@app.get("/bracket", response_class=HTMLResponse)
def bracket():
    return _serve_app()


@app.get("/app", response_class=HTMLResponse)
def app_alias():
    return _serve_app()


@app.get("/info", response_class=HTMLResponse)
def home():
    return """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Copa 2026 · Calendário Dinâmico</title>
<style>
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0a1f0a;color:#e8f5e9;
max-width:640px;margin:0 auto;padding:24px;line-height:1.6}
h1{color:#ffd700}code{background:#102a12;padding:2px 6px;border-radius:5px;font-size:13px}
.box{background:#102a12;border:1px solid #2a4a2c;border-radius:12px;padding:16px;margin:14px 0}
a{color:#1eb85a}ol{padding-left:20px}li{margin:6px 0}
</style></head><body>
<h1>🏆 Copa 2026 — Calendário Dinâmico</h1>
<p>Assine no Google Calendar e os jogos atualizam sozinhos (placar dos jogos disputados e
confrontos do mata-mata conforme são definidos).</p>
<div class="box">
<b>🎮 Bracket interativo (grupos + chaveamento):</b><br>
<a href="/bracket" style="font-size:16px">Abrir o chaveamento interativo →</a>
</div>
<div class="box">
<b>Calendário completo:</b><br><code id="full"></code><br><br>
<b>Só jogos do Brasil:</b><br><code id="br"></code>
</div>
<div class="box">
<b>Como assinar (atualiza sozinho):</b>
<ol>
<li>Abra o Google Calendar no computador</li>
<li>Menu lateral → <b>Outras agendas</b> → <b>+</b> → <b>De URL</b></li>
<li>Cole a URL acima (.ics) e clique em <b>Adicionar agenda</b></li>
<li>Pronto — o Google revisita a URL e atualiza sozinho (a cada 8–24h)</li>
</ol>
<small>Horários em Brasília. Jogos do Brasil têm lembrete 1h antes.</small>
</div>
<script>
const base=location.origin;
document.getElementById('full').textContent=base+'/copa2026.ics';
document.getElementById('br').textContent=base+'/brasil.ics';
</script>
</body></html>"""
