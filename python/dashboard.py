# SPDX-FileCopyrightText: Copyright (C) Arduino s.r.l. and/or its affiliated companies
#
# SPDX-License-Identifier: MPL-2.0

from arduino.app_utils import App, Bridge
from arduino.app_bricks.streamlit_ui import st
from datetime import datetime

# ============================================================
# CONTATORE DETRITI — persiste tra i refresh grazie a st.session_state
# Si azzera automaticamente ogni giorno (a mezzanotte)
# ============================================================
if "contatore_detriti" not in st.session_state:
    st.session_state.contatore_detriti = 0
    st.session_state.data_reset        = datetime.now().date()
    st.session_state.movimento_prec    = 0

# Azzera il contatore ogni nuovo giorno
if datetime.now().date() > st.session_state.data_reset:
    st.session_state.contatore_detriti = 0
    st.session_state.data_reset        = datetime.now().date()

# ============================================================
# DATI DA ARDUINO via Bridge
# ============================================================
try:
    distanza_mm     = Bridge.call("get_distanza")
    movimento       = Bridge.call("get_movimento")
    livello_arduino = Bridge.call("get_livello")
    livello_m       = max(0.0, 2.5 - (distanza_mm / 1000.0)) if distanza_mm > 0 else 0.0

except Exception:
    distanza_mm     = -1
    movimento       = 0
    livello_arduino = "NORMALE"
    livello_m       = 0.65

# Aggiorna contatore: incrementa solo al fronte di salita del movimento
# (evita di contare più volte lo stesso detrito)
if movimento == 1 and st.session_state.movimento_prec == 0:
    st.session_state.contatore_detriti += 1
st.session_state.movimento_prec = movimento

contatore = st.session_state.contatore_detriti

# Calcola livello detriti dal contatore
if contatore <= 5:
    livello_detriti = 1   # lieve / assente
elif contatore <= 20:
    livello_detriti = 2   # moderata
else:
    livello_detriti = 3   # elevata

# ============================================================
# CALCOLI LIVELLO ACQUA
# ============================================================
pct_css     = str(round(min((livello_m / 2.50) * 100, 100), 1))
livello_str = str(round(livello_m, 2)) + " m"

if livello_m < 0.10:
    stato   = "SECCA"
    c_stato = "#e74c3c"
elif livello_m < 0.20:
    stato   = "BASSO"
    c_stato = "#f1c40f"
elif livello_m <= 1.00:
    stato   = "NORMALE"
    c_stato = "#2ecc71"
elif livello_m <= 2.00:
    stato   = "ATTENZIONE"
    c_stato = "#f1c40f"
else:
    stato   = "PIENA"
    c_stato = "#e74c3c"

# ============================================================
st.set_page_config(
    page_title="Sorveglianza Murazzi - Po",
    page_icon="🌊",
    layout="wide"
)

st.title("🌊 Sistema di Sorveglianza del Po (Murazzi - Torino)")
st.markdown("### Sistema di monitoraggio delle piene e dei detriti")

col_sx, col_dx = st.columns([1, 2], gap="large")

# ============================================================
# PANNELLO SINISTRO — SEMAFORO DETRITI
# ============================================================
with col_sx:
    st.subheader("🗑️ Quantità di Detriti")

    rosso  = "#e74c3c" if livello_detriti == 3 else "#2d0000"
    giallo = "#f1c40f" if livello_detriti == 2 else "#2d2500"
    verde  = "#2ecc71" if livello_detriti <= 1 else "#002d10"

    sr = "box-shadow:0 0 24px 10px #e74c3c;" if livello_detriti == 3 else ""
    sg = "box-shadow:0 0 24px 10px #f1c40f;" if livello_detriti == 2 else ""
    sv = "box-shadow:0 0 24px 10px #2ecc71;" if livello_detriti <= 1 else ""

    contatore_str = str(contatore)
    reset_str     = st.session_state.data_reset.strftime("%d/%m/%Y")

    st.markdown(
        '<div style="background:#111;border:4px solid #555;border-radius:24px;'
        'width:110px;padding:18px 0;margin:0 auto;'
        'display:flex;flex-direction:column;align-items:center;gap:14px;">'
        '<div style="width:68px;height:68px;border-radius:50%;background:' + rosso + ';' + sr + '"></div>'
        '<div style="width:68px;height:68px;border-radius:50%;background:' + giallo + ';' + sg + '"></div>'
        '<div style="width:68px;height:68px;border-radius:50%;background:' + verde + ';' + sv + '"></div>'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown("<br>", unsafe_allow_html=True)

    labels = {1:"Lieve / Assente", 2:"Moderata", 3:"Elevata"}
    colori = {1:"#2ecc71", 2:"#f1c40f", 3:"#e74c3c"}
    st.markdown(
        '<h3 style="text-align:center;color:' + colori[livello_detriti] + '">'
        + labels[livello_detriti] + '</h3>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<p style="text-align:center;color:#aaa;font-size:16px;">Reset: ' + reset_str + '</p>',
        unsafe_allow_html=True
    )

# ============================================================
# PANNELLO DESTRO — BARRA LIVELLO ACQUA
# ============================================================
with col_dx:
    st.subheader("💧 Livello dell'Acqua")

    st.markdown(
        '<div style="display:inline-block;">'
        '<div style="display:flex;align-items:flex-start;gap:24px;margin-top:16px">'
        '<div style="position:relative;width:80px;height:260px;'
        'border:3px solid #555;border-radius:8px;overflow:hidden;background:#111;flex-shrink:0;">'
        '<div style="position:absolute;bottom:80%;left:0;right:0;height:20%;background:#5c0a0a;"></div>'
        '<div style="position:absolute;bottom:40%;left:0;right:0;height:40%;background:#5c4a00;"></div>'
        '<div style="position:absolute;bottom:8%;left:0;right:0;height:32%;background:#0a4a1f;"></div>'
        '<div style="position:absolute;bottom:4%;left:0;right:0;height:4%;background:#5c4a00;"></div>'
        '<div style="position:absolute;bottom:0;left:0;right:0;height:4%;background:#5c0a0a;"></div>'
        '<div style="position:absolute;bottom:' + pct_css + '%;left:0;right:0;'
        'height:4px;background:white;box-shadow:0 0 10px 4px white;"></div>'
        '</div>'
        '<div style="position:relative;height:260px;font-size:12px;color:#aaa;flex-shrink:0;">'
        '<div style="position:absolute;bottom:99%;white-space:nowrap;">2.50 m</div>'
        '<div style="position:absolute;bottom:80%;white-space:nowrap;">🔴 2.00 m — Piena</div>'
        '<div style="position:absolute;bottom:40%;white-space:nowrap;">🟡 1.00 m — Attenzione</div>'
        '<div style="position:absolute;bottom:8%;white-space:nowrap;">🟢 0.20 m — Normale</div>'
        '<div style="position:absolute;bottom:4%;white-space:nowrap;">🟡 0.10 m — Basso</div>'
        '<div style="position:absolute;bottom:0%;white-space:nowrap;">🔴 0.00 m — Secca</div>'
        '</div>'
        '</div>'
        '<h3 style="text-align:center;white-space:nowrap;margin-top:16px;color:' + c_stato + '">' + livello_str + ' — ' + stato + '</h3>'
        '</div>',
        unsafe_allow_html=True
    )
