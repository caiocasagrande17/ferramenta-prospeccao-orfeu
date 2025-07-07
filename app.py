# app.py

import streamlit as st
import pandas as pd
import googlemaps
import time
import requests
from bs4 import BeautifulSoup
import re

# --- CSS PERSONALIZADO ---
# MUDANÇA 3: Regras de CSS para a tabela (th, td, .st-emotion-cache-1y5v9b8) foram removidas.
page_style = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700&display=swap');
    
    /* --- GERAL --- */
    html, body, [class*="st-"], input, textarea, select, button {
        font-family: 'Manrope', sans-serif;
    }
    [data-testid="stAppViewContainer"] {
        background-color: #2E2015; /* Fundo principal marrom escuro */
    }
    [data-testid="stSidebar"] {
        background-color: #4A3728; /* Fundo da sidebar marrom */
    }
    h1, h2, h3, h4, h5, h6, p, label, .st-emotion-cache-16idsys p, th, td {
        color: #FAF7F2 !important; /* Texto principal cor creme (agora inclui a tabela novamente) */
    }

    /* --- FORMULÁRIOS E INPUTS --- */
    .st-emotion-cache-1pzk6v0, 
    .st-emotion-cache-16idsys, 
    textarea, 
    input {
        background-color: #F5EFE6 !important; /* Tom de areia bem claro */
        color: #2E2015 !important; /* Texto escuro para legibilidade */
        border-radius: 8px !important;
    }
    .st-emotion-cache-1q8dd3v span {
        background-color: #D2691E !important; /* Cor de destaque Orfeu */
        color: #FFFFFF !important;
    }

    /* --- BOTÃO --- */
    .stButton>button {
        background-color: #D2691E;
        color: #FFFFFF;
        border: none;
        border-radius: 8px;
    }
    .stButton>button:hover {
        background-color: #E5833E;
        color: #FFFFFF;
        border: none;
    }
    </style>
"""

# --- CONFIGURAÇÃO PRINCIPAL ---
MINHA_API_KEY = "AIzaSyB6s0tsf4IBO7b3YqDQmhp2YwpbRIUG_AI" 
EXCLUIR_NOMES = ["mcdonald's", "mc donald's", "mcdonalds", "burger king", "starbucks", "subway", "bob's", "kfc", "pizza hut"]

# --- SISTEMA DE PONTUAÇÃO (DATA-DRIVEN) ---
PONTOS_POR_TIPO = {'restaurant': 40, 'cafe': 40, 'bakery': 40, 'bar': 15, 'lodging': 20, 'spa': 15}
PONTOS_POR_PRECO = {2: 25, 1: 10, 3: 20, 4: 20}
BAIRROS_ESTRATEGICOS = ['barra da tijuca', 'centro', 'copacabana', 'leblon', 'ipanema']
BONUS_BAIRRO = 20

def raspar_contatos_do_site(url):
    if not url or not url.startswith('http'): return 'N/A', 'N/A'
    email_encontrado, instagram_encontrado = 'N/A', 'N/A'
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        resposta = requests.get(url, headers=headers, timeout=5)
        if resposta.status_code == 200:
            emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', resposta.text)
            if emails: email_encontrado = emails[0]
            soup = BeautifulSoup(resposta.text, 'html.parser')
            for link in soup.find_all('a', href=True):
                if 'instagram.com/' in link['href']:
                    instagram_encontrado = link['href']
                    break
    except requests.exceptions.RequestException: pass
    return email_encontrado, instagram_encontrado

def calcular_pontuacao(estabelecimento, bairro_prospect, precos_selecionados):
    score = 0
    tipo_place = estabelecimento.get('types', [])[0]
    score += PONTOS_POR_TIPO.get(tipo_place, 0)
    nota = estabelecimento.get('rating', 0)
    if nota >= 4.7: score += 50
    elif 4.3 <= nota < 4.7: score += 35
    elif 4.0 <= nota < 4.3: score += 10
    if precos_selecionados:
        faixa_preco = estabelecimento.get('price_level')
        score += PONTOS_POR_PRECO.get(faixa_preco, 0)
    if any(bairro_estrategico in bairro_prospect.lower() for bairro_estrategico in BAIRROS_ESTRATEGICOS):
        score += BONUS_BAIRRO
    num_avaliacoes = estabelecimento.get('user_ratings_total', 0)
    if num_avaliacoes > 300: score += 10
    elif num_avaliacoes >= 100: score += 5
    return round(score)

@st.cache_data(ttl=3600)
def buscar_detalhes_do_lugar(_gmaps_client, place_id):
    try:
        fields = ['name', 'formatted_phone_number', 'website']; details = _gmaps_client.place(place_id=place_id, fields=fields, language='pt-BR')
        return details.get('result', {})
    except Exception as e:
        st.error(f"Erro ao buscar detalhes para place_id {place_id}: {e}"); return {}

def prospectar_bairros(api_key, bairros, cidade, tipos, nota_range, precos, raio, min_avaliacoes):
    if not api_key or api_key == "COLE_SUA_CHAVE_DA_API_AQUI":
        st.error("ERRO: A chave da API não foi definida no código."); return pd.DataFrame()
    gmaps = googlemaps.Client(key=api_key)
    resultados_finais = []
    barra_progresso = st.progress(0, text="Iniciando prospecção...")
    for i, bairro in enumerate(bairros):
        if not bairro.strip(): continue
        barra_progresso.progress((i + 1) / len(bairros), text=f"Processando bairro: {bairro}...")
        try:
            geocode_result = gmaps.geocode(f"{bairro}, {cidade}")
            if not geocode_result: st.warning(f"Bairro '{bairro}' não encontrado em {cidade}."); continue
            loc = geocode_result[0]['geometry']['location']
        except Exception as e:
            st.error(f"Erro de geocodificação para '{bairro}, {cidade}': {e}"); continue
        for tipo in tipos:
            try:
                response = gmaps.places_nearby(location=loc, radius=raio, type=tipo, language='pt-BR')
                for place in response.get('results', []):
                    nome_place = place.get('name', '').lower()
                    num_avaliacoes = place.get('user_ratings_total', 0)
                    nome_excluido = any(excluir in nome_place for excluir in EXCLUIR_NOMES)
                    if (not nome_excluido and num_avaliacoes >= min_avaliacoes and
                        nota_range[0] <= place.get('rating', 0) <= nota_range[1] and
                        (not precos or place.get('price_level') is None or place.get('price_level') in precos)):
                        
                        detalhes = buscar_detalhes_do_lugar(gmaps, place['place_id'])
                        pontuacao = calcular_pontuacao(place, bairro, precos)
                        email, instagram = raspar_contatos_do_site(detalhes.get('website'))
                        
                        resultados_finais.append({
                            'Pontuação': pontuacao, 'Nome': place.get('name'), 'Nota Média': place.get('rating', 0),
                            'Nº de Avaliações': num_avaliacoes,
                            'Faixa de Preço': '$' * place.get('price_level', 0) if place.get('price_level') else 'N/A',
                            'Email': email, 'Instagram': instagram,
                            'Website': detalhes.get('website', 'N/A'),
                            'Telefone': detalhes.get('formatted_phone_number', 'N/A'),
                            'Endereço': place.get('vicinity'), 'Bairro': bairro,
                            'Tipo': tipo.replace('_', ' ').capitalize()
                        })
            except Exception as e: st.error(f"Erro ao buscar '{tipo}' em '{bairro}': {e}")
    barra_progresso.empty()
    if not resultados_finais: return pd.DataFrame()
    df = pd.DataFrame(resultados_finais)
    df = df.drop_duplicates(subset=['Nome', 'Endereço']).sort_values(by='Pontuação', ascending=False)
    return df

# --- INTERFACE DO USUÁRIO (STREAMLIT) ---
st.set_page_config(page_title="Prospecção B2B - Café Orfeu", layout="wide")
st.markdown(page_style, unsafe_allow_html=True)

# MUDANÇA 1: Título e Subtítulo alterados.
st.title("Ferramenta de Prospecção B2B - Café Orfeu")
st.subheader("Projeto Bairros")

st.sidebar.header("Parâmetros da Busca")
bairros_default = "\n".join(b.title() for b in BAIRROS_ESTRATEGICOS)
bairros_input = st.sidebar.text_area("Bairros (um por linha)", bairros_default, help="Insira um ou mais bairros, um por linha.")
cidade_input = st.sidebar.text_input("Cidade", "Rio de Janeiro")
tipos_disponiveis = ['restaurant', 'cafe', 'bakery', 'bar', 'lodging', 'spa']
tipos_selecionados = st.sidebar.multiselect("Tipos de Estabelecimento", options=tipos_disponiveis, default=['restaurant', 'cafe', 'bakery'])
precos_disponiveis = {'$': 1, '$$': 2, '$$$': 3, '$$$$': 4}
precos_selecionados_str = st.sidebar.multiselect("Faixa de Preço", options=precos_disponiveis.keys(), default=[], help="Deixe em branco para não filtrar por preço e ter uma pontuação mais justa.")
precos_selecionados_int = [precos_disponiveis[p] for p in precos_selecionados_str]
nota_selecionada = st.sidebar.slider("Nota Média Mínima e Máxima", 1.0, 5.0, (4.3, 5.0))
raio_selecionado = st.sidebar.slider("Raio da Busca (metros)", 500, 5000, 2000)
min_avaliacoes = st.sidebar.number_input("Nº Mínimo de Avaliações", min_value=0, value=10, help="Excluir locais com menos de N avaliações.")

if st.sidebar.button("🔍 Prospectar Agora"):
    bairros_lista = [b.strip() for b in bairros_input.split('\n') if b.strip()]
    if not bairros_lista: st.error("Por favor, insira pelo menos um bairro.")
    elif not cidade_input: st.error("Por favor, insira uma cidade.")
    else:
        with st.spinner(f"Buscando e analisando os melhores leads em {cidade_input}..."):
            df_resultados = prospectar_bairros(
                api_key=MINHA_API_KEY, bairros=bairros_lista, cidade=cidade_input, 
                tipos=tipos_selecionados, nota_range=nota_selecionada, 
                precos=precos_selecionados_int, raio=raio_selecionado, 
                min_avaliacoes=min_avaliacoes
            )
        st.success("Busca finalizada!")
        st.session_state['df_final'] = df_resultados

if 'df_final' in st.session_state and not st.session_state['df_final'].empty:
    df_para_exibir = st.session_state['df_final']
    st.header("Resultados da Prospecção")
    st.markdown("Leads ordenados por **pontuação**.")
    
    colunas_para_exibir = [
        'Pontuação', 'Nome', 'Email', 'Instagram', 'Telefone', 'Website', 
        'Nota Média', 'Nº de Avaliações', 'Faixa de Preço', 'Endereço', 'Bairro', 'Tipo'
    ]
    st.dataframe(df_para_exibir[colunas_para_exibir], hide_index=True)
    
    @st.cache_data
    def convert_df_to_csv(df):
        df_to_download = df[colunas_para_exibir]
        # MUDANÇA 2: Adicionado sep=';' para compatibilidade com Excel no Brasil/Europa.
        return df_to_download.to_csv(index=False, sep=';').encode('utf-8-sig')
    
    csv = convert_df_to_csv(df_para_exibir)
    st.download_button(label="📥 Baixar resultados como CSV", data=csv, file_name=f"prospeccao_orfeu.csv", mime="text/csv")

elif 'df_final' in st.session_state:
    st.warning("Nenhum resultado encontrado com os critérios especificados.")