# 🏥 Verifica Copertura Assicurativa

Cerca una prestazione sanitaria e scopri cosa rimborsa la tua assicurazione. Analisi AI in tempo reale sul tariffario originale.

## Come funziona

1. Carica il PDF del tariffario (una volta sola)
2. Il paziente cerca una prestazione
3. L'AI consulta le sezioni rilevanti del tariffario e risponde con dettagli su: rimborso, prescrizione, limiti annuali, documenti, copertura familiari, limitazioni

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

Serve una API key Anthropic (console.anthropic.com) — costo ~$0.01-0.03 per ricerca.

## Deploy su Streamlit Cloud

1. Push su GitHub
2. share.streamlit.io → New app → seleziona repo → main file: `app.py` → Deploy
