# app.py

import streamlit as st
import pandas as pd
import googlemaps
from googlemaps.convert import decode_polyline
import time
import requests
from bs4 import BeautifulSoup
import re
import folium
import streamlit.components.v1 as components
from urllib.parse import quote
import qrcode
from io import BytesIO
import google.generativeai as genai

# --- CSS PERSONALIZADO ---
page_style = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700&display=swap');
    html, body, [class*="st-"], input, textarea, select, button { font-family: 'Manrope', sans-serif; }
    [data-testid="stAppViewContainer"] { background-color: #2E2015; }
    [data-testid="stSidebar"] { background-color: #4A3728; }
    h1, h2, h3, h4, h5, h6, p, label, .st-emotion-cache-16idsys p, th, td { color: #FAF7F2 !important; }
    .st-emotion-cache-1pzk6v0, .st-emotion-cache-16idsys, textarea, input { background-color: #F5EFE6 !important; color: #2E2015 !important; border-radius: 8px !important; }
    .st-emotion-cache-1q8dd3v span { background-color: #D2691E !important; color: #FFFFFF !important; }
    .stButton>button { background-color: #D2691E; color: #FFFFFF; border: none; border-radius: 8px; font-weight: 600; }
    .stButton>button:hover { background-color: #E5833E; color: #FFFFFF; border: none; }
    div[data-testid="stDownloadButton"] > button { background-color: #2E2015 !important; color: #FFFFFF !important; border: 1px solid #FAF7F2 !important; }
    div[data-testid="stDownloadButton"] > button:hover { background-color: #4A3728 !important; color: #FFFFFF !important; border: 1px solid #D2691E !important; }
    [data-testid="stLinkButton"] a {
        background-color: #2E2015 !important; color: #FFFFFF !important; border: 1px solid #FFFFFF !important;
        padding: 0.5em 1em; border-radius: 8px; text-decoration: none; display: inline-block; text-align: center;
    }
    [data-testid="stLinkButton"] a:hover { border-color: #D2691E !important; background-color: #4A3728 !important; }
    </style>
"""

# --- CONFIGURAÇÃO DAS CHAVES DE API (USO LOCAL) ---
MINHA_API_KEY = "COLE_SUA_CHAVE_DA_API_AQUI" 
GEMINI_API_KEY = "COLE_SUA_CHAVE_GEMINI_AQUI"

if GEMINI_API_KEY and GEMINI_API_KEY != "COLE_SUA_CHAVE_GEMINI_AQUI":
    genai.configure(api_key=GEMINI_API_KEY)
else:
    st.sidebar.warning("Chave da API Gemini não inserida. A personalização de mensagens por IA está desativada.")
    GEMINI_API_KEY = None

# --- CONSTANTES E LISTAS ---
EXCLUIR_NOMES = ["mcdonald's", "mc donald's", "mcdonalds", "burger king", "starbucks", "subway", "bob's", "kfc", "pizza hut", "cacau show", "parme", "parmê", "rei do mate", "mega matte"]
PONTOS_POR_TIPO = {'restaurant': 40, 'cafe': 40, 'bakery': 40, 'bar': 15, 'lodging': 20, 'spa': 15}
PONTOS_POR_PRECO = {2: 25, 1: 10, 3: 20, 4: 20}
BAIRROS_ESTRATEGICOS = ['barra da tijuca', 'centro', 'copacabana', 'leblon', 'ipanema']
BONUS_BAIRRO = 20
MENSAGEM_PROSPECCAO_PADRAO = "Olá! Sou da Café Orfeu e gostaria de apresentar nossos cafés especiais. Seria um prazer agendar uma breve demonstração. Podemos conversar?"

# --- FUNÇÕES AUXILIARES ---
def normalizar_telefone(numero):
    if isinstance(numero, str): return re.sub(r'\D', '', numero)
    return ''

def gerar_link_whatsapp(telefone, texto):
    if not telefone or telefone == 'N/A' or not texto: return None
    telefone_limpo = normalizar_telefone(telefone)
    if not telefone_limpo.startswith('55'):
        telefone_limpo = '55' + telefone_limpo
    texto_encoded = quote(texto)
    return f"https://wa.me/{telefone_limpo}?text={texto_encoded}"

def gerar_link_email(email, assunto, corpo):
    if not email or email == 'N/A': return None
    assunto_encoded = quote(assunto)
    corpo_encoded = quote(corpo)
    return f"mailto:{email}?subject={assunto_encoded}&body={corpo_encoded}"

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
                    instagram_encontrado = link['href']; break
    except requests.exceptions.RequestException: pass
    return email_encontrado, instagram_encontrado

def calcular_pontuacao(estabelecimento, bairro_prospect, precos_selecionados):
    score = 0; tipo_place = estabelecimento.get('types', [])[0]; score += PONTOS_POR_TIPO.get(tipo_place, 0)
    nota = estabelecimento.get('rating', 0)
    if nota >= 4.7: score += 50
    elif 4.3 <= nota < 4.7: score += 35
    elif 4.0 <= nota < 4.3: score += 10
    if precos_selecionados:
        faixa_preco = estabelecimento.get('price_level'); score += PONTOS_POR_PRECO.get(faixa_preco, 0)
    if any(bairro_estrategico in bairro_prospect.lower() for bairro_estrategico in BAIRROS_ESTRATEGICOS): score += BONUS_BAIRRO
    num_avaliacoes = estabelecimento.get('user_ratings_total', 0)
    if num_avaliacoes > 300: score += 10
    elif num_avaliacoes >= 100: score += 5
    return round(score)

def criar_mapa_interativo(df, rota_coords=None):
    if df.empty or 'Latitude' not in df.columns or 'Longitude' not in df.columns: return None
    lat_media = df['Latitude'].mean(); lng_media = df['Longitude'].mean()
    mapa = folium.Map(location=[lat_media, lng_media], zoom_start=13, tiles="CartoDB positron")
    
    for i, row in df.iterrows():
        display_name = f"{i+1}. {row['Nome']}"
        popup_html = f"<b>{display_name}</b><br>Pontuação: {row['Pontuação']}<br>Endereço: {row['Endereço']}"
        popup = folium.Popup(popup_html, max_width=300)
        folium.Marker(
            location=[row['Latitude'], row['Longitude']], popup=popup, tooltip=display_name,
            icon=folium.features.CustomIcon('https://img.icons8.com/plasticine/100/marker.png', icon_size=(30,30))
        ).add_to(mapa)
    if rota_coords:
        folium.PolyLine(rota_coords, color="red", weight=3.5, opacity=0.8).add_to(mapa)
        mapa.fit_bounds(folium.PolyLine(rota_coords).get_bounds())
    return mapa

@st.cache_data(ttl=600)
def gerar_rota_otimizada(_gmaps_client, df_rota, modo):
    if len(df_rota) < 2: return None
    origem_addr = df_rota.iloc[0]['Endereço']
    waypoints_addr = [row['Endereço'] for _, row in df_rota.iloc[1:].iterrows()]
    try:
        direcoes = _gmaps_client.directions(
            origin=origem_addr, destination=origem_addr, waypoints=waypoints_addr,
            mode=modo.lower(), optimize_waypoints=True
        )
        if not direcoes: st.error("Não foi possível calcular uma rota com os pontos selecionados."); return None
        ordem_otimizada = direcoes[0]['waypoint_order']
        pontos_ordenados = [waypoints_addr[i] for i in ordem_otimizada]
        url_waypoints = "|".join([quote(p) for p in pontos_ordenados])
        url_Maps = f"https://www.google.com/maps/dir/?api=1&origin={quote(origem_addr)}&destination={quote(origem_addr)}&waypoints={url_waypoints}"
        polyline = direcoes[0]['overview_polyline']['points']
        rota_decodificada = decode_polyline(polyline)
        coords = [(d['lat'], d['lng']) for d in rota_decodificada]
        df_reordenado = pd.concat([df_rota.iloc[[0]], df_rota.iloc[[i + 1 for i in ordem_otimizada]]]).reset_index(drop=True)
        return {"coords": coords, "url": url_Maps, "dataframe": df_reordenado}
    except Exception as e:
        st.error(f"Erro ao calcular a rota: {e}"); return None

@st.cache_data(ttl=3600)
def gerar_mensagem_ia(reviews, nome_estabelecimento):
    if not GEMINI_API_KEY or not reviews:
        return MENSAGEM_PROSPECCAO_PADRAO
    
    texto_reviews = "\n".join([f"- {r['text']}" for r in reviews if r.get('text')])
    if not texto_reviews: return MENSAGEM_PROSPECCAO_PADRAO

    prompt = f"""
    Assuma a persona de um vendedor B2B sênior e muito experiente da Café Orfeu, uma marca de cafés especiais de luxo. Sua comunicação é elegante, confiante e focada em criar um relacionamento.
    Seu objetivo é redigir uma mensagem de WhatsApp para o primeiro contato com o gestor do estabelecimento '{nome_estabelecimento}'.
    Analise as avaliações de clientes abaixo para encontrar um gancho autêntico.
    ---
    {texto_reviews}
    ---
    Com base nisso, crie a mensagem (máximo 3 frases) que elogie um aspecto único do negócio, conecte sutilmente à qualidade do nosso café, e finalize com uma pergunta leve e aberta. Comece de forma direta, sem "Olá".
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return MENSAGEM_PROSPECCAO_PADRAO

@st.cache_data(ttl=3600)
def buscar_detalhes_do_lugar(_gmaps_client, place_id):
    try:
        # Busca agora pede 'reviews' para a IA, e foi simplificada
        fields = ['name', 'formatted_phone_number', 'website', 'reviews']
        details = _gmaps_client.place(place_id=place_id, fields=fields, language='pt-BR')
        return details.get('result', {})
    except Exception as e:
        st.error(f"Erro ao buscar detalhes para place_id {place_id}: {e}"); return {}

def prospectar_bairros(api_key, bairros, cidade, tipos, nota_range, precos, raio, min_avaliacoes, keyword):
    if not api_key or "COLE_SUA_CHAVE" in api_key:
        st.error("ERRO: A chave da API do Google Maps não foi definida no código."); return pd.DataFrame()
    gmaps = googlemaps.Client(key=api_key)
    resultados_finais = []
    barra_progresso = st.progress(0, text="Iniciando prospecção...")
    for i, bairro_busca in enumerate(bairros):
        if not bairro_busca.strip(): continue
        barra_progresso.progress((i + 1) / len(bairros), text=f"Processando bairro: {bairro_busca}...")
        try:
            geocode_result = gmaps.geocode(f"{bairro_busca}, {cidade}");
            if not geocode_result: st.warning(f"Bairro '{bairro_busca}' não encontrado."); continue
            loc = geocode_result[0]['geometry']['location']
        except Exception as e:
            st.error(f"Erro de geocodificação para '{bairro_busca}, {cidade}': {e}"); continue
        for tipo in tipos:
            try:
                response = gmaps.places_nearby(location=loc, radius=raio, type=tipo, language='pt-BR', keyword=keyword)
                for place in response.get('results', []):
                    nome_place = place.get('name', '').lower(); num_avaliacoes = place.get('user_ratings_total', 0)
                    nome_excluido = any(excluir in nome_place for excluir in EXCLUIR_NOMES)
                    if (not nome_excluido and num_avaliacoes >= min_avaliacoes and
                        nota_range[0] <= place.get('rating', 0) <= nota_range[1] and
                        (not precos or place.get('price_level') is None or place.get('price_level') in precos)):
                        
                        detalhes = buscar_detalhes_do_lugar(gmaps, place['place_id'])
                        pontuacao = calcular_pontuacao(place, bairro_busca, precos)
                        email, instagram = raspar_contatos_do_site(detalhes.get('website'))
                        lat, lng = place['geometry']['location']['lat'], place['geometry']['location']['lng']
                        
                        resultados_finais.append({
                            'Pontuação': pontuacao, 'Nome': place.get('name'), 
                            'Nota Média': place.get('rating', 0), 'Nº de Avaliações': num_avaliacoes,
                            'Faixa de Preço': '$' * place.get('price_level', 0) if place.get('price_level') else 'N/A',
                            'Email': email, 'Instagram': instagram,
                            'Website': detalhes.get('website', 'N/A'), 'URL Google Maps': place.get('url', 'N/A'),
                            'Telefone': detalhes.get('formatted_phone_number', 'N/A'),
                            'Endereço': place.get('vicinity'), 'Tipo': tipo.replace('_', ' ').capitalize(),
                            'Latitude': lat, 'Longitude': lng, 'Reviews_API': detalhes.get('reviews', [])
                        })
            except Exception as e: st.error(f"Erro ao buscar '{tipo}' em '{bairro_busca}': {e}")
    barra_progresso.empty()
    if not resultados_finais: return pd.DataFrame()
    df = pd.DataFrame(resultados_finais).drop_duplicates(subset=['Nome', 'Endereço']).sort_values(by=['Pontuação'], ascending=False)
    return df

# --- INTERFACE DO USUÁRIO ---
st.set_page_config(page_title="Prospecção B2B - Café Orfeu", layout="wide")
st.markdown(page_style, unsafe_allow_html=True)
st.title("Ferramenta de Prospecção B2B - Café Orfeu")
st.subheader("Projeto Bairros")
st.sidebar.header("Parâmetros da Busca")
st.sidebar.divider()
bairros_default = "\n".join(b.title() for b in BAIRROS_ESTRATEGICOS)
bairros_input = st.sidebar.text_area("Bairros", bairros_default, help="Insira um ou mais bairros, um por linha.")
cidade_input = st.sidebar.text_input("Cidade", "Rio de Janeiro")
tipos_disponiveis = ['restaurant', 'cafe', 'bakery', 'bar', 'lodging', 'spa']
tipos_selecionados = st.sidebar.multiselect("Tipos de Estabelecimento", options=tipos_disponiveis, default=['restaurant', 'cafe', 'bakery'])
keyword_input = st.sidebar.text_input("Palavra-chave para refinar busca (opcional)", placeholder="Ex: sorveteria, gourmet, pizzaria")
precos_disponiveis = {'$': 1, '$$': 2, '$$$': 3, '$$$$': 4}
precos_selecionados_str = st.sidebar.multiselect("Faixa de Preço", options=precos_disponiveis.keys(), default=[], help="Deixe em branco para não filtrar.")
precos_selecionados_int = [precos_disponiveis[p] for p in precos_selecionados_str]
nota_selecionada = st.sidebar.slider("Nota Média", 1.0, 5.0, (4.3, 5.0))
raio_selecionado = st.sidebar.slider("Raio da Busca (m)", 500, 5000, 2000)
min_avaliacoes = st.sidebar.number_input("Mínimo de Avaliações", min_value=0, value=10)

if st.sidebar.button("🔍 Prospectar Agora"):
    bairros_lista = [b.strip() for b in bairros_input.split('\n') if b.strip()]
    if not bairros_lista: st.error("Por favor, insira pelo menos um bairro.")
    elif not cidade_input: st.error("Por favor, insira uma cidade.")
    else:
        with st.spinner(f"Buscando e analisando leads em {cidade_input}..."):
            df_resultados = prospectar_bairros(
                api_key=MINHA_API_KEY, bairros=bairros_lista, cidade=cidade_input, 
                tipos=tipos_selecionados, nota_range=nota_selecionada, 
                precos=precos_selecionados_int, raio=raio_selecionado, 
                min_avaliacoes=min_avaliacoes, keyword=keyword_input
            )
        st.session_state['df_final'] = df_resultados
        if 'rota_info' in st.session_state: del st.session_state['rota_info']

if 'df_final' in st.session_state and not st.session_state['df_final'].empty:
    df_para_exibir = st.session_state['df_final'].copy()
    
    with st.spinner("Gerando mensagens personalizadas com IA... (pode levar um tempo)"):
        df_para_exibir['Mensagem_IA'] = df_para_exibir.apply(lambda row: gerar_mensagem_ia(row['Reviews_API'], row['Nome']), axis=1)
    
    df_para_exibir['Ação WhatsApp'] = df_para_exibir.apply(lambda row: gerar_link_whatsapp(row['Telefone'], row['Mensagem_IA']), axis=1)
    df_para_exibir['Ação Email'] = df_para_exibir['Email'].apply(lambda email: gerar_link_email(email, "Contato Comercial - Café Orfeu", MENSAGEM_PROSPECCAO_PADRAO))

    st.sidebar.divider()
    st.sidebar.header("Otimizador de Rota")
    pontuacao_minima_rota = st.sidebar.slider("Pontuação mínima para rota", 0, 150, 50, key="pontuacao_rota")
    num_visitas = st.sidebar.slider("Número de locais a visitar", 2, 10, 5, key="num_visitas_rota")
    mapa_modos = {"Dirigindo 🚗": "driving", "Andando 🚶": "walking"}
    modo_selecionado_pt = st.sidebar.radio("Modo de transporte", list(mapa_modos.keys()))
    
    if st.sidebar.button("📍 Otimizar Rota de Visita"):
        modo_transporte_en = mapa_modos[modo_selecionado_pt]
        df_filtrado = df_para_exibir[df_para_exibir['Pontuação'] >= pontuacao_minima_rota]
        df_top = df_filtrado.head(num_visitas)
        if len(df_top) >= 2:
            with st.spinner("Calculando a rota mais eficiente..."):
                gmaps_client = googlemaps.Client(key=MINHA_API_KEY)
                rota_info = gerar_rota_otimizada(gmaps_client, df_top, modo_transporte_en)
                st.session_state['rota_info'] = rota_info
        else:
            st.sidebar.warning("Não há locais suficientes com os critérios de rota.")

    if 'rota_info' in st.session_state and st.session_state['rota_info']:
        rota_info = st.session_state['rota_info']
        st.header("Rota de Visita Otimizada")
        mapa_com_rota = criar_mapa_interativo(rota_info['dataframe'], rota_coords=rota_info['coords'])
        if mapa_com_rota:
            components.html(mapa_com_rota._repr_html_(), height=400)
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("Abrir no Celular")
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(rota_info['url']); qr.make(fit=True)
            img = qr.make_image(fill='black', back_color='white')
            buf = BytesIO(); img.save(buf, format="PNG")
            st.image(buf)
            st.link_button("Abrir Rota no Navegador", rota_info['url'])
        with col2:
            st.subheader("Ordem de Visitação")
            df_rota_display = rota_info['dataframe'][['Nome', 'Endereço', 'Pontuação']].reset_index(drop=True)
            df_rota_display.index += 1
            st.dataframe(df_rota_display, use_container_width=True)
    else:
        st.header("Visualização Geográfica dos Leads")
        mapa_leads = criar_mapa_interativo(df_para_exibir)
        if mapa_leads:
            components.html(mapa_leads._repr_html_(), height=450)

    st.header("Lista Completa de Resultados")
    
    colunas_para_exibir = [
        'Pontuação', 'Nome', 'Tipo', 'Endereço', 
        'Nota Média', 'Nº de Avaliações', 'Telefone', 'Ação WhatsApp', 
        'Email', 'Ação Email', 'Website', 'Instagram', 'Faixa de Preço'
    ]
    st.dataframe(
        df_para_exibir[[col for col in colunas_para_exibir if col in df_para_exibir.columns]], 
        hide_index=True, height=600, use_container_width=True,
        column_config={
            "Ação WhatsApp": st.column_config.LinkColumn("WhatsApp", display_text="Contatar 💬"),
            "Ação Email": st.column_config.LinkColumn("Email", display_text="Contatar ✉️")
        }
    )
    
    @st.cache_data
    def convert_df_to_csv(df):
        return df.to_csv(index=False, sep=';').encode('utf-8-sig')
    csv = convert_df_to_csv(df_para_exibir)
    st.download_button(label="📥 Baixar resultados como CSV", data=csv, file_name=f"prospeccao_orfeu.csv", mime="text/csv")
elif 'df_final' in st.session_state:
    st.warning("Nenhum resultado encontrado com os critérios especificados.")