# Semana de Frota

Pipeline público que gera a visão de ocupação da frota da garagem
**Matriz — Belo Horizonte** (Grupo Saritur), 95 carros, dias 03–06/09/2026.

Artifact: <https://claude.ai/code/artifact/e9044cd7-4c82-4ab1-874a-c247b535edc4>

## Uso

```bash
python run.py
```

Baixa a planilha pública **FROTA MOVIMENTO**
(<https://docs.google.com/spreadsheets/d/19t_XZetIEYahWVyizp8w1Y371FDtnPBNXheTIkW9oSU>),
reconstrói a linha do tempo e grava `semana_frota.html`.
Depois, publicar esse arquivo **no mesmo artifact** (parâmetro `url`).

Só stdlib do Python 3 — sem `pip install`.

## Arquivos

- `run.py` — baixa, parseia, monta a linha do tempo, gera o HTML
- `template.html` — casca da visão; recebe os dados via `__PAYLOAD__`
- `semana_frota.html` — saída gerada (não editar à mão)

## Notas do modelo

- Coluna **B** da planilha = nº de ordem; **H/I/J/K** = Qui/Sex/Sáb/Dom.
- Tempo de viagem: duração real da tabela horária do site de vendas Saritur,
  embutida em `TT` no `run.py` (consulta de 04/09/2026). Cidade nova sem tempo
  conhecido cai numa estimativa de 4 h marcada como "estimado".
- Sentido: `bh` no ponto de saída → ida; caso contrário → volta.
- Viagem que passa da meia-noite reaparece no início do dia seguinte.
