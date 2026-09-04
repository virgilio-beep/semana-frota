# -*- coding: utf-8 -*-
"""
Semana de Frota — pipeline único e autossuficiente.

Baixa a planilha FROTA MOVIMENTO (Google Sheets, link público), reconstrói a
linha do tempo de viagens dos 95 carros da garagem Matriz-BH nos dias
03–06/09/2026 e gera `semana_frota.html`.

Rodar:  python run.py
Saída:  semana_frota.html  (publicar no Artifact
        https://claude.ai/code/artifact/e9044cd7-4c82-4ab1-874a-c247b535edc4)

Sem dependências externas (só stdlib). Se `requests`/`httpx` não existirem,
usa urllib.
"""
import csv, io, json, os, re, sys, unicodedata

SHEET_CSV = ("https://docs.google.com/spreadsheets/d/"
             "19t_XZetIEYahWVyizp8w1Y371FDtnPBNXheTIkW9oSU/export?format=csv&gid=0")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_HTML = os.path.join(HERE, "semana_frota.html")

DIAS = ["H", "I", "J", "K"]
DATA = {"H": "2026-09-03", "I": "2026-09-04", "J": "2026-09-05", "K": "2026-09-06"}
DIA_NOME = {"H": "Qui 03/09", "I": "Sex 04/09", "J": "Sáb 05/09", "K": "Dom 06/09"}
BH = {"BH", "BELO", "BELOHORIZONTE"}

# destino (ponta oposta a BH) por número de linha normalizado
OVERRIDES = {
    "1108": "Santo Antonio do Rio Abaixo", "1155": "Carmesia", "1155A": "Carmesia",
    "1043": "Itajuba", "1119": "Sao Sebastiao do Paraiso", "1309": "Ouro Fino",
    "1178": "Guaxupe", "1072": "Alfenas", "1072A": "Alfenas", "1075": "Pocos de Caldas",
    "1050": "Cassia", "10501": "Passos", "10532": "Lagoa da Prata", "1053": "Lagoa da Prata",
    "1097": "Santana do Riacho", "1097A": "Santana do Riacho", "1047": "Ferros", "10472": "Ferros",
    "1140": "Oliveira", "1013": "Itabira", "10131": "Itabira", "10621": "Pecanha",
    "1062A": "Sao Jose da Safira", "1063A": "Sao Jose da Safira", "1087": "Sabinopolis",
    "10871": "Sabinopolis", "10872": "Materlandia", "1162": "Agua Boa", "5784": "Baldim",
    "5785": "Baldim", "1217": "Capelinha", "1218": "Itamarandiba", "1214": "Malacacheta",
    "1020": "Itambe do Mato Dentro", "1078": "Passa Tempo", "10755": "Pocos de Caldas",
    "1075 5": "Varginha",
}

# tempo de viagem real (min) da tabela horária do site de vendas Saritur — (ida, volta)
# ida = BH -> interior ; volta = interior -> BH. Consulta de 04/09/2026.
TT = {
    "Santo Antonio do Rio Abaixo": (290, 290), "Carmesia": (250, 310),
    "Sao Sebastiao do Paraiso": (480, 485), "Ouro Fino": (585, 585), "Alfenas": (395, 385),
    "Guaxupe": (540, 600), "Pocos de Caldas": (480, 480), "Cassia": (460, 520),
    "Passos": (375, 420), "Santana do Riacho": (240, 240), "Oliveira": (195, 165),
    "Itabira": (105, 100), "Passa Tempo": (140, 140), "Pecanha": (335, 350),
    "Sao Jose da Safira": (540, 560), "Ferros": (190, 250), "Materlandia": (325, 430),
    "Agua Boa": (460, 445), "Baldim": (130, 130), "Capelinha": (685, 720),
    "Itamarandiba": (430, 455), "Malacacheta": (507, 560), "Itambe do Mato Dentro": (185, 200),
    "Sabinopolis": (290, 345), "Lagoa da Prata": (255, 230), "Varginha": (325, 315),
    "Itajuba": (450, 540),
}
TT_DEFAULT = (240, 240)  # cidade nova sem tempo conhecido

# ------------------------------------------------------------------ util
def na(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s).lower())
                   if unicodedata.category(c) != "Mn")

def norm_linha(s):
    return re.sub(r"[^0-9A-Za-z]", "", str(s)).upper()

def hhm(m):
    return f"{m // 60}h{m % 60:02d}"

CACHE_CSV = os.path.join(HERE, "frota_movimento.csv")

def _fetch_live():
    """Tenta baixar a planilha ao vivo. Levanta exceção se a rede estiver
    bloqueada (comum em sandboxes de agente na nuvem com egress restrito) ou
    se a planilha não estiver pública."""
    import urllib.request
    req = urllib.request.Request(SHEET_CSV, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=45).read()
    txt = raw.decode("utf-8", "replace")
    if "<html" in txt[:200].lower():
        raise RuntimeError("a planilha não está pública (retornou HTML de login) — "
                           "ajuste o compartilhamento para 'qualquer pessoa com o link'")
    return txt

def baixar_csv():
    """Preferência: dado ao vivo do Google Sheets. Se a rede estiver
    bloqueada (ex.: sandbox de rotina agendada sem egress p/ docs.google.com),
    cai pro `frota_movimento.csv` versionado no repo -- mantido fresco por um
    GitHub Action (.github/workflows/refresh-planilha.yml) que roda a cada
    30 min a partir de uma runner com internet livre."""
    erro_rede = None
    try:
        txt = _fetch_live()
        try:
            with open(CACHE_CSV, "w", encoding="utf-8", newline="") as f:
                f.write(txt)
        except OSError:
            pass  # cache é um bônus; sem permissão de escrita não é fatal
        return list(csv.reader(io.StringIO(txt)))
    except Exception as e:
        erro_rede = e

    if os.path.exists(CACHE_CSV):
        idade_min = (__import__("time").time() - os.path.getmtime(CACHE_CSV)) / 60
        print(f"AVISO: rede bloqueada ({erro_rede}); usando frota_movimento.csv em cache "
              f"(~{idade_min:.0f} min desatualizado).")
        with open(CACHE_CSV, encoding="utf-8") as f:
            return list(csv.reader(f))

    sys.exit(f"ERRO baixando a planilha (sem rede e sem cache local): {erro_rede}")

# ------------------------------------------------------------------ parse
def rota_para_destino(rota):
    r = rota.upper().replace("EXTRA", "")
    r = re.split(r" VIA | POR | - ", r)[0]
    for w in (" MATUTINO", " NOTURNO", " DIURNO"):
        r = r.replace(w, "")
    parts = [p.strip() for p in re.split(r"\s*[X/]\s*", r) if p.strip()]
    cand = [p for p in parts if p not in ("BH", "BELO HORIZONTE", "RESERVA")]
    return cand[0].title() if cand else None

SPLIT = re.compile(r"\s+-\s*|\s*-\s+|\s*/\s*|\n+")
ISLINE = re.compile(r"^(?:CH\s*)?\d{3,5}(?:[A-Za-z]|-?\d)?$", re.I)
ISTIME = re.compile(r"^(\d{1,2}):(\d{2})(?:\s+(.*))?$")

def parse_cell(c):
    c = c.strip()
    low = c.lower()
    if not c:
        return [], False, "sem registro"
    if c.upper() == "S/E":
        return [], False, "sem escala"
    if "vistoria" in low:
        return [], False, "vistoria/manutenção"
    if not re.search(r"\d{1,2}:\d{2}", c):
        return [], False, c
    toks = [t.strip() for t in SPLIT.split(c) if t.strip()]
    legs, chegando, last_line, line_pending = [], False, None, False
    for t in toks:
        mt = ISTIME.match(t)
        if re.match(r"^ch\s*\d", t, re.I):
            chegando = True
            last_line = norm_linha(re.sub(r"(?i)^ch", "", t))
            line_pending = True
            continue
        if t.lower() == "ch":
            chegando = True
            continue
        if mt:
            hh, mm = int(mt.group(1)), int(mt.group(2))
            legs.append([last_line, hh * 60 + mm, f"{hh:02d}:{mm:02d}", (mt.group(3) or "").strip()])
            line_pending = False
            continue
        if ISLINE.match(t):
            last_line = norm_linha(t)
            line_pending = True
            continue
        if line_pending and re.match(r"^\d$", t):
            last_line = norm_linha(f"{last_line}{t}")
            continue
        if legs and not legs[-1][3]:
            legs[-1][3] = t
    legs = [l for l in legs if l[0]]
    return legs, chegando, (None if legs else c)

def parse(rows):
    linha_dest = dict(OVERRIDES)
    veic = []
    for r in rows[2:]:
        if len(r) < 11 or not r[1].strip():
            continue
        carro, modelo, prefixo, rota, status = (r[1].strip(), r[2].strip(), r[3].strip(),
                                                r[4].strip(), r[5].strip())
        d = rota_para_destino(rota)
        if d and prefixo and prefixo.upper() != "RESERVA":
            linha_dest.setdefault(norm_linha(prefixo), d)
        veic.append(dict(carro=carro, modelo=modelo, prefixo=prefixo, rota=rota, status=status,
                         dias={k: r[7 + i].strip() for i, k in enumerate("HIJK")}))
    regs = {}
    for v in veic:
        for k, cell in v["dias"].items():
            legs, chegando, nota = parse_cell(cell)
            regs[(v["carro"], k)] = dict(raw=cell.strip(), chegando=chegando, nota=nota, legs=[
                dict(linha=ln, dep_min=dep, dep_hhmm=hhmm, origem_tok=place)
                for ln, dep, hhmm, place in legs])
    return veic, regs, linha_dest

# ------------------------------------------------------------------ timeline
def tempos(cidade):
    if not cidade:
        return TT_DEFAULT[0], TT_DEFAULT[1], "estimado"
    key = next((c for c in TT if na(c) == na(cidade)), None)
    if key:
        return TT[key][0], TT[key][1], "saritur"
    return TT_DEFAULT[0], TT_DEFAULT[1], "estimado"

def build(veic, regs, linha_dest):
    N = len(veic)
    dias_out = []
    for d in DIAS:
        linhas = []
        for v in veic:
            r = regs.get((v["carro"], d))
            intervals, estado, nota, chegando = [], "parado", None, False
            if norm_linha(v.get("status")) == "PARADO":
                linhas.append(dict(carro=v["carro"], modelo=v["modelo"], prefixo=v["prefixo"],
                                   rota=v["rota"], estado="indisponivel", nota="PARADO",
                                   chegando=False, raw=(r["raw"] if r else ""), intervals=[]))
                continue
            if r:
                if r["nota"] and not r["legs"]:
                    t = r["nota"].lower()
                    if "sem escala" in t:
                        estado, nota = "sem_escala", "S/E"
                    elif "vistoria" in t or "manut" in t:
                        estado, nota = "manutencao", r["nota"]
                    elif "sem registro" in t:
                        estado = "parado"
                    else:
                        estado, nota = "nota", r["nota"]
                chegando = r["chegando"]
                for l in r["legs"]:
                    ln = l["linha"]
                    dest = linha_dest.get(ln, "?")
                    i_min, v_min, fonte = tempos(linha_dest.get(ln))
                    ini = l["dep_min"]
                    otok = norm_linha(l["origem_tok"])
                    if otok in BH:
                        tipo, sent, dur = "ida", f"BH → {dest}", i_min
                    elif otok:
                        tipo, sent, dur = "volta", f"{dest} → BH", v_min
                    else:
                        tipo, sent, dur = "viagem", f"linha {dest}", i_min
                    fim_raw = ini + dur
                    intervals.append(dict(ini=ini, fim=min(fim_raw, 1440), fim_raw=fim_raw,
                                          overflow=fim_raw > 1440, tipo=tipo, fonte=fonte,
                                          rot=f'L{ln} · sai {l["dep_hhmm"]} · {sent} · ~{hhm(dur)}'))
            linhas.append(dict(carro=v["carro"], modelo=v["modelo"], prefixo=v["prefixo"],
                               rota=v["rota"], estado=estado, nota=nota, chegando=chegando,
                               raw=(r["raw"] if r else ""), intervals=intervals))
        dias_out.append(dict(dia=d, nome=DIA_NOME[d], linhas=linhas, agg=[0] * 48))

    # continuação na madrugada do dia seguinte
    cont = 0
    for di in range(3):
        for i in range(N):
            prox = dias_out[di + 1]["linhas"][i]
            for it in dias_out[di]["linhas"][i]["intervals"]:
                if not it.get("overflow"):
                    continue
                tail = min(it["fim_raw"] - 1440, 1439)
                if prox["chegando"]:
                    for j in prox["intervals"]:
                        if j["tipo"] == "chegando":
                            j["fim"] = max(j["fim"], tail)
                            j["rot"] = f'chegando a BH · fim ~{hhm(tail)} (segue de {DIA_NOME[DIAS[di]]})'
                            j["fonte"] = it["fonte"]
                else:
                    prox["intervals"].insert(0, dict(
                        ini=0, fim=tail, fim_raw=tail, overflow=False, tipo=it["tipo"],
                        fonte=it["fonte"], continuacao=True,
                        rot=f'continua de {DIA_NOME[DIAS[di]]}: {it["rot"]} · chega ~{hhm(tail)}'))
                    cont += 1
                if prox["estado"] == "parado":
                    prox["estado"] = "operando"

    # chegando sem origem (dia 1) -> estimativa
    for i in range(N):
        l = dias_out[0]["linhas"][i]
        if l["chegando"] and not any(it["tipo"] == "chegando" for it in l["intervals"]):
            first = min((it["ini"] for it in l["intervals"]), default=None)
            arr = 300 if first is None else max(120, min(first - 45, 360))
            l["intervals"].insert(0, dict(ini=0, fim=arr, fim_raw=arr, overflow=False,
                                          tipo="chegando", fonte="—",
                                          rot="chegando a BH (viagem da madrugada anterior)"))

    for dd in dias_out:
        for l in dd["linhas"]:
            for it in l["intervals"]:
                if it["tipo"] == "chegando":
                    continue
                b0, b1 = it["ini"] // 30, min(47, (it["fim"] - 1) // 30)
                for b in range(max(0, b0), b1 + 1):
                    dd["agg"][b] += 1
            l["mins_op"] = sum(it["fim"] - it["ini"] for it in l["intervals"]
                               if it["tipo"] != "chegando")
            if l["intervals"] and l["estado"] == "parado":
                l["estado"] = "operando"

    resumo = []
    for dd in dias_out:
        ops = [l for l in dd["linhas"] if l["mins_op"] > 0]
        pk = dd["agg"].index(max(dd["agg"])) if any(dd["agg"]) else 0
        resumo.append(dict(dia=dd["nome"], carros_ativos=len(ops),
                           pico=max(dd["agg"]) if any(dd["agg"]) else 0,
                           pico_h=f'{pk // 2:02d}:{"30" if pk % 2 else "00"}',
                           horas_frota=round(sum(l["mins_op"] for l in dd["linhas"]) / 60)))
    sem = [round(sum(dias_out[d]["linhas"][i]["mins_op"] for d in range(4)) / 60, 1)
           for i in range(N)]
    usadas = {ln for r in regs.values() for ln in [l["linha"] for l in r["legs"]]}
    reais = sorted({linha_dest[ln] for ln in usadas
                    if linha_dest.get(ln) and any(na(c) == na(linha_dest[ln]) for c in TT)})
    est = sorted({linha_dest[ln] for ln in usadas
                  if linha_dest.get(ln) and not any(na(c) == na(linha_dest[ln]) for c in TT)})
    parados_n = sum(1 for v in veic if norm_linha(v.get("status")) == "PARADO")
    return dict(frota_total=N, dias=dias_out, resumo=resumo, sem_semana=sem,
                parados_n=parados_n, reais_cidades=reais, est_cidades=est,
                linha_dest=linha_dest)

# ------------------------------------------------------------------ html
def gerar_html(data):
    tpl_path = os.path.join(HERE, "template.html")
    with open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html = tpl.replace("__PAYLOAD__", payload)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"escrito: {OUT_HTML}  ({len(html)} bytes)")

def main():
    rows = baixar_csv()
    veic, regs, linha_dest = parse(rows)
    data = build(veic, regs, linha_dest)
    for r in data["resumo"]:
        print(r)
    print("estimados ainda:", data["est_cidades"])
    gerar_html(data)

if __name__ == "__main__":
    main()
