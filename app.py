import plotly.express as px
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from twilio.rest import Client
import os

# Chargement des variables d'environnement (si en local)
from dotenv import load_dotenv
load_dotenv()

# Config Streamlit
st.set_page_config(page_title="Suivi de Stock BTP", page_icon="🏗️")
st.title("🏗️ Suivi de Stock Matériaux et Matériels BTP avec Prédiction de Rupture (Created by A.Madjid)")

# Initialisation des DataFrames
if "stock_df" not in st.session_state:
    st.session_state.stock_df = pd.DataFrame(columns=["Matériau", "Quantité", "Date dernière mise à jour", "Seuil critique"])

if "historique" not in st.session_state:
    st.session_state.historique = pd.DataFrame(columns=["Date", "Matériau", "Quantité", "Type"])  # Type: Entrée ou Sortie

# Formulaire de livraison (entrée)
st.header("🚚 Nouvelle livraison")
with st.form("form_livraison"):
    materiau = st.selectbox("Matériau", ["Ciment", "Fer", "Sable", "Gravier", "Briques", "Autre"])
    quantite = st.number_input("Quantité livrée", min_value=0.0, step=1.0)
    seuil = st.number_input("Seuil critique", min_value=0.0, step=1.0, value=10.0)
    submit_livraison = st.form_submit_button("Ajouter")

    if submit_livraison:
        now = datetime.now()
        if materiau in st.session_state.stock_df["Matériau"].values:
            idx = st.session_state.stock_df[st.session_state.stock_df["Matériau"] == materiau].index[0]
            st.session_state.stock_df.at[idx, "Quantité"] += quantite
            st.session_state.stock_df.at[idx, "Date dernière mise à jour"] = now.strftime("%Y-%m-%d %H:%M")
            st.session_state.stock_df.at[idx, "Seuil critique"] = seuil
        else:
            new_row = {
                "Matériau": materiau,
                "Quantité": quantite,
                "Date dernière mise à jour": now.strftime("%Y-%m-%d %H:%M"),
                "Seuil critique": seuil,
            }
            st.session_state.stock_df = pd.concat([st.session_state.stock_df, pd.DataFrame([new_row])], ignore_index=True)

        st.session_state.historique = pd.concat([
            st.session_state.historique,
            pd.DataFrame([{"Date": now, "Matériau": materiau, "Quantité": quantite, "Type": "Entrée"}])
        ], ignore_index=True)
        st.success(f"{quantite} unités de {materiau} livrées.")

# Retrait
st.header("🏗️ Utilisation chantier")
if not st.session_state.stock_df.empty:
    materiau_sortie = st.selectbox("Matériau utilisé", st.session_state.stock_df["Matériau"])
    quantite_sortie = st.number_input("Quantité utilisée", min_value=0.0, step=1.0)
    if st.button("Retirer du stock"):
        idx = st.session_state.stock_df[st.session_state.stock_df["Matériau"] == materiau_sortie].index[0]
        if quantite_sortie <= st.session_state.stock_df.at[idx, "Quantité"]:
            st.session_state.stock_df.at[idx, "Quantité"] -= quantite_sortie
            now = datetime.now()
            st.session_state.stock_df.at[idx, "Date dernière mise à jour"] = now.strftime("%Y-%m-%d %H:%M")
            st.session_state.historique = pd.concat([
                st.session_state.historique,
                pd.DataFrame([{"Date": now, "Matériau": materiau_sortie, "Quantité": quantite_sortie, "Type": "Sortie"}])
            ], ignore_index=True)
            st.success(f"{quantite_sortie} unités de {materiau_sortie} retirées.")
        else:
            st.error("Stock insuffisant pour ce retrait.")

# Stock + prédiction + SMS
st.header("📊 Stock Actuel avec Prédiction de Rupture")
if not st.session_state.stock_df.empty:
    for _, row in st.session_state.stock_df.iterrows():
        mat = row["Matériau"]
        qty = row["Quantité"]
        seuil = row["Seuil critique"]
        couleur = "🟢" if qty >= seuil else "🔴"

        # Consommation moyenne
        recent_data = st.session_state.historique[
            (st.session_state.historique["Matériau"] == mat) &
            (st.session_state.historique["Type"] == "Sortie") &
            (st.session_state.historique["Date"] >= datetime.now() - timedelta(days=7))
        ]

        if not recent_data.empty:
            total_used = recent_data["Quantité"].sum()
            nb_jours = (datetime.now() - recent_data["Date"].min()).days + 1
            conso_journalière = total_used / nb_jours
            jours_restant = qty / conso_journalière if conso_journalière > 0 else "∞"
            pred = f"⏳ Rupture dans {jours_restant:.1f} jours" if isinstance(jours_restant, float) else "🔋 Pas de consommation récente"
        else:
            pred = "🔋 Pas de consommation récente"

        st.markdown(f"**{mat}** : {couleur} {qty} unités — {pred}")

        # Envoi SMS si seuil atteint
        if qty < seuil:
            try:
                client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
                sender = os.getenv("TWILIO_PHONE_NUMBER")
                dests = os.getenv("DEST_NUMBERS", "").split(",")
                for dest in dests:
                    if dest.strip():
                        client.messages.create(
                            body=f"⚠️ Stock critique de {mat} : {qty} unités restantes.",
                            from_=sender,
                            to=dest.strip()
                        )
            except Exception as e:
                st.warning(f"Erreur d'envoi SMS : {e}")

else:
    st.info("Aucun stock enregistré pour le moment.")

# Graphique d’évolution
st.header("📈 Évolution du stock dans le temps")
if not st.session_state.historique.empty:
    materiaux_dispo = st.session_state.historique["Matériau"].unique()
    mat_select = st.selectbox("Choisir un matériau", materiaux_dispo)

    historique_mat = st.session_state.historique[
        st.session_state.historique["Matériau"] == mat_select
    ].sort_values("Date")

    stock_temps = []
    total = 0
    for _, row in historique_mat.iterrows():
        if row["Type"] == "Entrée":
            total += row["Quantité"]
        elif row["Type"] == "Sortie":
            total -= row["Quantité"]
        stock_temps.append({"Date": row["Date"], "Stock": total})

    df_plot = pd.DataFrame(stock_temps)

    if not df_plot.empty:
        fig = px.line(df_plot, x="Date", y="Stock", title=f"Évolution du stock de {mat_select}")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Aucune donnée suffisante pour tracer le graphique.")
else:
    st.info("Aucune donnée historique pour afficher un graphique.")
