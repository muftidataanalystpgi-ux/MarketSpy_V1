#tambah menu baru brand saturasi, metrix dsb
import streamlit as pd_st
import asyncio
from playwright.async_api import async_playwright
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
import re
import io
import os
import numpy as np

# Trik Otomatisasi Instalasi Biner Playwright di Server Cloud
if not os.path.exists("/home/adminuser/.cache/ms-playwright"):
    os.system("playwright install chromium")

# =============================================================================
# CONFIGURATION & HEADER
# =============================================================================
pd_st.set_page_config(page_title="MarketSpy & Analytics", layout="wide")

pd_st.title("MarketSpy & Analytics Platform")
pd_st.markdown(
    "Jalankan pencarian kompetitor, kumpulkan prospek penjualan (*leads*), "
    "dan analisis data pasar secara *real-time* dalam satu ekosistem digital."
)

# Initialize session state agar data hasil scraping tidak hilang saat berpindah tab/interaksi
if "saas_df" not in pd_st.session_state:
    pd_st.session_state.saas_df = None
if "current_keyword" not in pd_st.session_state:
    pd_st.session_state.current_keyword = ""

# =============================================================================
# HELPER FUNCTIONS & SCRAPER ENGINE (BACKEND)
# =============================================================================
def clean_text(text):
    if not text: 
        return "Tidak terdeteksi"
    cleaned = re.sub(r'[^\x00-\x7F]+', '', text)
    return cleaned.strip()

def extract_lat_lng(url):
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match: 
        return match.group(1), match.group(2)
    return "N/A", "N/A"

def preprocess_data(df_raw):
    data = df_raw.copy()
    if 'Rating' in data.columns:
        data['Rating_Murni'] = data['Rating'].astype(str).str.extract(r'([0-9\.]+)').astype(float)
        data['Total_Ulasan'] = data['Rating'].astype(str).str.extract(r'\((\d+)\)').fillna(0).astype(int)
    else:
        data['Rating_Murni'] = np.nan
        data['Total_Ulasan'] = 0
        
    data['Latitude'] = pd.to_numeric(data['Latitude'], errors='coerce')
    data['Longitude'] = pd.to_numeric(data['Longitude'], errors='coerce')
    
    # Deteksi Kelas Reputasi untuk segmentasi analisis data
    def classify_reputation(rating):
        if pd.isna(rating):
            return "No Rating"
        elif rating >= 4.5:
            return "Premium Class"
        elif rating >= 4.0:
            return "Standard Class"
        else:
            return "Underperforming"
            
    data['Kelas_Reputasi'] = data['Rating_Murni'].apply(classify_reputation)
    return data

# Hitung Jarak Euclidean Sederhana (Pendekatan Cepat Tanpa Lib Eksternal)
def calculate_simple_distance(lat1, lon1, lat2, lon2):
    return np.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2) * 111  # Konversi kasar ke kilometer

async def run_google_maps_scraper(keyword, status_ui):
    async with async_playwright() as p:
        status_ui.text("Menginisialisasi sistem web browser virtual...")
        
        # MODIFIKASI DISINI: Tambahkan args sandbox untuk Streamlit Cloud
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        search_url = f"https://www.google.com/maps/search/{keyword}/"
        status_ui.text(f"Mengirim query pencarian untuk: '{keyword}'...")
        await page.goto(search_url)
        
        try:
            await page.wait_for_selector('div[role="feed"]', timeout=10000)
        except Exception:
            await browser.close()
            return None
        
        status_ui.text("Membuka gulungan peta (Scrolling feed)...")
        for i in range(15):  # Dioptimalkan demi kecepatan performa respons SaaS
            feed = await page.query_selector('div[role="feed"]')
            if feed:
                await feed.evaluate("element => element.scrollBy(0, 4000)")
                await page.wait_for_timeout(1000)
        
        place_elements = await page.query_selector_all('a[href*="/maps/place/"]')
        urls_to_scrape = []
        for el in place_elements:
            href = await el.get_attribute('href')
            if href and href not in urls_to_scrape:
                urls_to_scrape.append(href)
        
        total_urls = len(urls_to_scrape)
        status_ui.text(f"Ditemukan {total_urls} titik potensial. Memulai ekstraksi detail...")
        
        extracted_data = []
        for index, target_url in enumerate(urls_to_scrape):
            try:
                status_ui.text(f"[Proses {index+1}/{total_urls}] Mengekstrak data...")
                await page.goto(target_url)
                
                try:
                    await page.wait_for_url(lambda url: "@" in url, timeout=4000)
                except:
                    await page.wait_for_timeout(1000)
                
                latitude, longitude = extract_lat_lng(page.url)
                nama_el = await page.query_selector('h1')
                nama = clean_text(await nama_el.inner_text()) if nama_el else "Tanpa Nama"
                
                rating = "N/A"
                rating_el = await page.query_selector('div.F7nice')
                if rating_el: 
                    rating = (await rating_el.inner_text()).replace("\n", " ")
                
                alamat = "Tidak terdeteksi"
                address_el = await page.query_selector('button[data-item-id="address"]')
                if address_el: 
                    alamat = await address_el.inner_text()
                
                telepon = "Tidak ada"
                phone_el = await page.query_selector('button[data-item-id^="phone:tel:"]')
                if phone_el: 
                    telepon = await phone_el.inner_text()
                
                website = "Belum punya"
                web_el = await page.query_selector('a[data-item-id="authority"]')
                if web_el: 
                    website = await web_el.get_attribute('href') or "Belum punya"
                
                extracted_data.append({
                    "Nama Tempat": nama, "Rating": clean_text(rating),
                    "No. Telepon": clean_text(telepon), "Alamat": clean_text(alamat),
                    "Website": website, "Latitude": latitude, "Longitude": longitude
                })
            except:
                continue
                
        await browser.close()
        return extracted_data

# =============================================================================
# FRONTEND CONTROL CENTER (DASHBOARD)
# =============================================================================
with pd_st.container(border=True):
    col_search, col_action = pd_st.columns([4, 1])
    with col_search:
        input_keyword = pd_st.text_input("Masukkan Kata Kunci Pasar & Lokasi Target", placeholder="Contoh: kontraktor di depok, seblak bandung").strip()
    with col_action:
        pd_st.write("##") # Spacer untuk menyamakan baris tombol
        start_button = pd_st.button("Mulai Scrape & Analisis", type="primary", use_container_width=True)

if start_button:
    if not input_keyword:
        pd_st.error("Gagal! Kata kunci pencarian tidak boleh dibiarkan kosong.")
    else:
        status_placeholder = pd_st.empty()
        with pd_st.spinner("Mengaktifkan cloud worker engine..."):
            raw_results = asyncio.run(run_google_maps_scraper(input_keyword, status_placeholder))
        
        status_placeholder.empty()
        
        if raw_results:
            df_processed = preprocess_data(pd.DataFrame(raw_results))
            pd_st.session_state.saas_df = df_processed
            pd_st.session_state.current_keyword = input_keyword
            pd_st.success(f"Analisis Selesai! Berhasil merangkum {len(df_processed)} entitas pasar.")
        else:
            pd_st.error("Pencarian gagal. Google Maps tidak mengembalikan hasil, silakan periksa kata kunci Anda.")

# =============================================================================
# ANALYTICS DASHBOARD TABS
# =============================================================================
if pd_st.session_state.saas_df is not None:
    df = pd_st.session_state.saas_df
    keyword_safe = pd_st.session_state.current_keyword.replace(" ", "_")

    # --- TABS LAYOUT (MENGINTEGRASIKAN TOTAL 8 ANALISIS MENU) ---
    tab_geo, tab_reputation, tab_digital, tab_brand, tab_benchmarking, tab_saturation, tab_sentiment, tab_leads_mgmt = pd_st.tabs([
        " Geospatial Analytics", 
        " Reputation Analytics", 
        " Digital Readiness", 
        " Brand Consistency",
        " Competitor Benchmarking",
        " Saturation Index",
        " Sentiment & Trends",
        " Leads Management (CRM)"
    ])
    
    # -------------------------------------------------------------------------
    # TAB 1: GEOSPATIAL ANALYTICS
    # -------------------------------------------------------------------------
    with tab_geo:
        pd_st.subheader("Analisis Pemetaan Spasial Komersial")
        df_geo = df.dropna(subset=['Latitude', 'Longitude'])
        
        if not df_geo.empty:
            m_col1, m_col2 = pd_st.columns(2)
            m_col1.metric("Koordinat Sukses Terpetakan", f"{len(df_geo)} Cabang")
            m_col2.metric("Koordinat Gagal Ditemukan (N/A)", f"{len(df) - len(df_geo)} Cabang")
            
            # Peta Folium dengan pewarnaan dinamis berbasis rating kualitas pelayanan
            map_center = [df_geo['Latitude'].mean(), df_geo['Longitude'].mean()]
            m = folium.Map(location=map_center, zoom_start=11)
            marker_cluster = MarkerCluster().add_to(m)
            
            for _, row in df_geo.iterrows():
                r = row['Rating_Murni']
                pin_color = 'green' if r >= 4.5 else 'orange' if r >= 4.0 else 'red' if r < 4.0 else 'blue'
                
                popup_box = f"""
                <div style='font-family: Arial, sans-serif; min-width: 220px; line-height: 1.5;'>
                    <h4 style='margin:0 0 5px 0; color:#333;'>{row['Nama Tempat']}</h4>
                    <b>⭐ Rating:</b> {row['Rating']}<br>
                    <b>📞 Telepon:</b> {row['No. Telepon']}<br>
                    <b>📍 Alamat:</b> {row['Alamat']}
                </div>
                """
                folium.Marker(
                    location=[row['Latitude'], row['Longitude']],
                    popup=folium.Popup(popup_box, max_width=320),
                    icon=folium.Icon(color=pin_color, icon='briefcase', prefix='fa')
                ).add_to(marker_cluster)
            
            st_folium(m, width=1300, height=500)
            pd_st.markdown("🟢 **Premium Class (>= 4.5)** | 🟡 **Standard Class (4.0 - 4.4)** | 🔴 **Underperforming (< 4.0)** | 🔵 **No Rating Data**")
        else:
            pd_st.error("Sistem tidak mendeteksi koordinat geolokasi yang valid pada data ini.")

    # -------------------------------------------------------------------------
    # TAB 2: REPUTATION ANALYTICS
    # -------------------------------------------------------------------------
    with tab_reputation:
        pd_st.subheader("Metrik Analisis Reputasi & Kepuasan Konsumen")
        
        df_valid_rating = df.dropna(subset=['Rating_Murni'])
        bad_branches = df_valid_rating[(df_valid_rating['Rating_Murni'] <= 4.0) & (df_valid_rating['Rating_Murni'] > 0)]
        
        rep_col1, rep_col2, rep_col3 = pd_st.columns(3)
        rep_col1.metric("Rerata Rating Pasar", f"{df_valid_rating['Rating_Murni'].mean():.2f} / 5.0" if not df_valid_rating.empty else "N/A")
        rep_col2.metric("Review Terbanyak (Popularitas)", f"{int(df['Total_Ulasan'].max())} Ulasan")
        rep_col3.metric("Butuh Evaluasi QC (Rating <= 4.0)", f"{len(bad_branches)} Titik")
        
        g_layout1, g_layout2 = pd_st.columns([3, 2])
        with g_layout1:
            fig_hist = px.histogram(df_valid_rating, x="Rating_Murni", nbins=12,
                                    title="Distribusi Kesehatan Rating Kompetitor",
                                    labels={'Rating_Murni': 'Skala Bintang Toko'},
                                    color_discrete_sequence=['#10B981'])
            pd_st.plotly_chart(fig_hist, use_container_width=True)
        with g_layout2:
            fig_scat = px.scatter(df, x="Total_Ulasan", y="Rating_Murni", hover_name="Nama Tempat",
                                  title="Matriks Korelasi Volume Review vs Kualitas Toko",
                                  labels={'Total_Ulasan': 'Jumlah Total Review', 'Rating_Murni': 'Rating'},
                                  color_discrete_sequence=['#3B82F6'])
            pd_st.plotly_chart(fig_scat, use_container_width=True)
            
        pd_st.write("Daftar Kategori Lampu Merah (Rating <= 4.0)")
        if not bad_branches.empty:
            bad_branches_sorted = bad_branches.sort_values(by='Rating_Murni', ascending=True)
            pd_st.dataframe(bad_branches_sorted[['Nama Tempat', 'Rating', 'No. Telepon', 'Alamat']], use_container_width=True)
        else:
            pd_st.success("Luar biasa! Tidak ditemukan kategori Lampu Merah (Rating <= 4.0).")

    # -------------------------------------------------------------------------
    # TAB 3: DIGITAL READINESS & AUDIT
    # -------------------------------------------------------------------------
    with tab_digital:
        pd_st.subheader("Audit Penetrasi Infrastruktur Digital")
        
        total_items = len(df)
        has_website_count = len(df[df['Website'] != 'Belum punya'])
        has_phone_count = len(df[df['No. Telepon'] != 'Tidak ada'])
        
        d_col1, d_col2 = pd_st.columns(2)
        with d_col1:
            fig_p1 = px.pie(names=["Miliki Website", "Buta Website"], 
                            values=[has_website_count, total_items - has_website_count], 
                            title="Tingkat Kepemilikan Website Komersial", hole=0.4,
                            color_discrete_sequence=['#2ECC71', '#E74C3C'])
            pd_st.plotly_chart(fig_p1, use_container_width=True)
        with d_col2:
            fig_p2 = px.pie(names=["Miliki Kontak", "Tidak Ada Kontak"], 
                            values=[has_phone_count, total_items - has_phone_count], 
                            title="Aksesibilitas Komunikasi (Telepon)", hole=0.4,
                            color_discrete_sequence=['#3498DB', '#BDC3C7'])
            pd_st.plotly_chart(fig_p2, use_container_width=True)
            
        pd_st.write("Hot Leads Generator (Target Prospek Prioritas Utama)")
        pd_st.warning("Daftar di bawah mengekstrak badan usaha yang belum mengoptimalkan website. Sangat disarankan untuk target penetrasi agensi pemasaran/pembuatan software.")
        leads_df = df[df['Website'] == 'Belum punya'][['Nama Tempat', 'No. Telepon', 'Alamat']]
        pd_st.dataframe(leads_df, use_container_width=True)

    # -------------------------------------------------------------------------
    # TAB 4: BRAND CONSISTENCY
    # -------------------------------------------------------------------------
    with tab_brand:
        pd_st.subheader("Audit Standardisasi & Konsistensi Identitas Brand")
        
        text_stream = " ".join(df['Nama Tempat'].astype(str)).lower()
        cleaned_words = [w for w in text_stream.split() if len(w) > 3 and w not in ['dan', 'yang', 'dengan', 'toko', 'kedai', 'depok', 'jakarta']]
        word_freq = pd.Series(cleaned_words).value_counts().head(10).reset_index()
        word_freq.columns = ['Token Kata', 'Frekuensi Pemakaian']
        
        b_col1, b_col2 = pd_st.columns([2, 3])
        with b_col1:
            pd_st.write("#### Top Keyword Dominan Pada Nama")
            pd_st.dataframe(word_freq, use_container_width=True)
        with b_col2:
            fig_words = px.bar(word_freq, x="Frekuensi Pemakaian", y="Token Kata", orientation='h',
                               title="Pola Kata Kunci Nama di Lapangan", color="Frekuensi Pemakaian",
                               color_continuous_scale=px.colors.sequential.Viridis)
            pd_st.plotly_chart(fig_words, use_container_width=True)
            
        pd_st.write("Master Database Hasil Ekstraksi Lapangan")
        pd_st.dataframe(df[['Nama Tempat', 'Rating', 'No. Telepon', 'Alamat', 'Website']], use_container_width=True)

    # -------------------------------------------------------------------------
    # TAB 5: COMPETITOR BENCHMARKING & MATRIX
    # -------------------------------------------------------------------------
    with tab_benchmarking:
        pd_st.subheader(" Competitor Performance Matrix")
        pd_st.markdown("Analisis kuadran komparatif membagi kompetitor berdasarkan popularitas (volume ulasan) dan tingkat loyalitas pelanggan (rating).")
        
        # Penentuan median/benchmark sebagai titik tengah kuadran
        median_rating = df_valid_rating['Rating_Murni'].median() if not df_valid_rating.empty else 4.0
        median_reviews = df_valid_rating['Total_Ulasan'].median() if not df_valid_rating.empty else 10
        
        fig_quadrant = px.scatter(
            df_valid_rating, 
            x="Total_Ulasan", 
            y="Rating_Murni", 
            hover_name="Nama Tempat",
            color="Kelas_Reputasi",
            title=f"Scatter Kuadran Pasar (Median Rating: {median_rating:.1f}, Median Review: {int(median_reviews)})",
            labels={'Total_Ulasan': 'Volume Ulasan Pelanggan', 'Rating_Murni': 'Skor Rating Bintang'},
            color_discrete_map={"Premium Class": "#10B981", "Standard Class": "#F59E0B", "Underperforming": "#EF4444", "No Rating": "#9CA3AF"}
        )
        
        # Tambahkan garis kuadran
        fig_quadrant.add_vline(x=median_reviews, line_dash="dash", line_color="gray", annotation_text="Benchmark Volume")
        fig_quadrant.add_hline(y=median_rating, line_dash="dash", line_color="gray", annotation_text="Benchmark Rating")
        pd_st.plotly_chart(fig_quadrant, use_container_width=True)
        
        # Tabel perbandingan interaktif
        pd_st.write(" **Bandingkan Langsung Beberapa Brand**")
        selected_brands = pd_st.multiselect("Pilih kompetitor untuk diaudit:", options=df['Nama Tempat'].unique(), default=df['Nama Tempat'].unique()[:3] if len(df) >=3 else df['Nama Tempat'].unique())
        
        if selected_brands:
            compare_df = df[df['Nama Tempat'].isin(selected_brands)][['Nama Tempat', 'Rating_Murni', 'Total_Ulasan', 'Website', 'No. Telepon']]
            pd_st.dataframe(compare_df, use_container_width=True)

    # -------------------------------------------------------------------------
    # TAB 6: MARKET DENSITY & SATURATION INDEX
    # -------------------------------------------------------------------------
    with tab_saturation:
        pd_st.subheader("Market Density & Saturation Index")
        pd_st.markdown("Mengukur kejenuhan pasar kompetitor sejenis dalam wilayah tangkapan geografis.")
        
        df_coords = df_geo.copy()
        if len(df_coords) > 1:
            # Hitung rata-rata jarak terdekat ke kompetitor (Nearest Neighbor Distance)
            distances = []
            for i, row_i in df_coords.iterrows():
                min_dist = float('inf')
                for j, row_j in df_coords.iterrows():
                    if i == j:
                        continue
                    dist = calculate_simple_distance(row_i['Latitude'], row_i['Longitude'], row_j['Latitude'], row_j['Longitude'])
                    if dist < min_dist:
                        min_dist = dist
                distances.append(min_dist)
            
            df_coords['Jarak_Kompetitor_Terdekat_KM'] = distances
            avg_nearest_distance = np.mean(distances)
            
            # Tentukan indeks saturasi
            if avg_nearest_distance < 0.5:
                saturation_status = "SANGAT PADAT (Hiper-Kompetitif)"
                color_sat = "red"
                sat_desc = "Kompetitor saling berdekatan dalam radius < 500 meter. Perang harga sangat rawan terjadi."
            elif avg_nearest_distance < 1.5:
                saturation_status = "CUKUP PADAT (Kompetitif)"
                color_sat = "orange"
                sat_desc = "Kepadatan standar perkotaan. Diferensiasi layanan atau optimasi SEO lokal sangat krusial."
            else:
                saturation_status = "LENGANG (Potensi Blue Ocean)"
                color_sat = "green"
                sat_desc = "Kepadatan sangat rendah. Peluang ekspansi pasar baru terbuka lebar tanpa persaingan ketat fisik."
            
            sat_col1, sat_col2 = pd_st.columns(2)
            sat_col1.metric("Rerata Jarak Antar Cabang", f"{avg_nearest_distance:.2f} KM")
            sat_col2.markdown(f"Status Kepadatan Wilayah: <span style='color:{color_sat};font-weight:bold;font-size:20px;'>{saturation_status}</span>", unsafe_allow_html=True)
            pd_st.info(sat_desc)
            
            # Grafik Distribusi Jarak
            fig_dist = px.box(df_coords, y="Jarak_Kompetitor_Terdekat_KM", 
                              title="Penyebaran Jarak Jangkauan Fisik Antar Kompetitor (KM)",
                              color_discrete_sequence=['#8B5CF6'])
            pd_st.plotly_chart(fig_dist, use_container_width=True)
        else:
            pd_st.warning("Data koordinat spasial kompetitor terlalu sedikit untuk mengalkulasi kepadatan wilayah.")

    # -------------------------------------------------------------------------
    # TAB 7: SENTIMENT & TREND ANALYTICS
    # -------------------------------------------------------------------------
    with tab_sentiment:
        pd_st.subheader("Sentiment & Trend Analytics (Simulated Social Listening)")
        pd_st.markdown("Analisis korelasi nama entitas dengan persepsi pasar guna melacak tren penamaan dan indikasi kepuasan sentimen.")
        
        # Simulasi analisis sentimen berbasis anomali ulasan rendah & tinggi
        df_sent = df_valid_rating.copy()
        if not df_sent.empty:
            def estimate_sentiment(row):
                if row['Rating_Murni'] >= 4.5:
                    return "Positif"
                elif row['Rating_Murni'] >= 4.0:
                    return "Netral"
                else:
                    return "Negatif"
            
            df_sent['Sentimen_Pasar'] = df_sent.apply(estimate_sentiment, axis=1)
            
            sent_counts = df_sent['Sentimen_Pasar'].value_counts().reset_index()
            sent_counts.columns = ['Status Sentimen', 'Jumlah']
            
            sc_col1, sc_col2 = pd_st.columns([2, 3])
            with sc_col1:
                fig_sent_pie = px.pie(sent_counts, names="Status Sentimen", values="Jumlah",
                                      title="Proporsi Sentimen Layanan Pasar",
                                      color="Status Sentimen",
                                      color_discrete_map={"Positif": "#10B981", "Netral": "#F59E0B", "Negatif": "#EF4444"})
                pd_st.plotly_chart(fig_sent_pie, use_container_width=True)
            with sc_col2:
                # Word Trend Analisis
                trend_words = []
                for idx, r in df_sent.iterrows():
                    cleaned_name = re.sub(r'[^\w\s]', '', r['Nama Tempat'].lower())
                    for token in cleaned_name.split():
                        if len(token) > 4 and token not in ['toko', 'depok', 'indonesia', 'jakarta', 'cabang']:
                            trend_words.append({"Kata": token, "Sentimen": r['Sentimen_Pasar']})
                
                if trend_words:
                    df_trends = pd.DataFrame(trend_words)
                    df_grouped = df_trends.groupby(['Kata', 'Sentimen']).size().unstack(fill_value=0).reset_index()
                    df_grouped['Total'] = df_grouped.get('Positif', 0) + df_grouped.get('Netral', 0) + df_grouped.get('Negatif', 0)
                    df_grouped = df_grouped.sort_values(by='Total', ascending=False).head(10)
                    
                    fig_trend_bar = px.bar(df_grouped, x='Kata', y=['Positif', 'Netral', 'Negatif'],
                                           title="Kata Kunci Merek & Hubungan Sentimen Reputasi",
                                           color_discrete_map={"Positif": "#10B981", "Netral": "#F59E0B", "Negatif": "#EF4444"})
                    pd_st.plotly_chart(fig_trend_bar, use_container_width=True)
                else:
                    pd_st.write("Ketersediaan kata kunci tidak mencukupi untuk melakukan analisis tren.")

    # -------------------------------------------------------------------------
    # TAB 8: LEAD MANAGEMENT & CRM EXPORT
    # -------------------------------------------------------------------------
    with tab_leads_mgmt:
        pd_st.subheader("Lead Export & CRM Integration")
        pd_st.markdown("Filter prospek prospektif Anda sesuai target kriteria pemasaran, lalu ekspor langsung ke format yang Anda butuhkan.")
        
        # Kontrol Filter Interaktif
        col_f1, col_f2, col_f3 = pd_st.columns(3)
        with col_f1:
            filter_web = pd_st.selectbox("Status Kepemilikan Website:", ["Semua", "Hanya yang Belum Punya Website", "Hanya yang Memiliki Website"])
        with col_f2:
            filter_contact = pd_st.selectbox("Status Kontak Telepon:", ["Semua", "Hanya yang Punya Kontak", "Hanya yang Tanpa Kontak"])
        with col_f3:
            filter_class = pd_st.multiselect("Kelas Reputasi:", options=df['Kelas_Reputasi'].unique(), default=df['Kelas_Reputasi'].unique())
            
        # Terapkan Filter
        filtered_leads = df.copy()
        if filter_web == "Hanya yang Belum Punya Website":
            filtered_leads = filtered_leads[filtered_leads['Website'] == 'Belum punya']
        elif filter_web == "Hanya yang Memiliki Website":
            filtered_leads = filtered_leads[filtered_leads['Website'] != 'Belum punya']
            
        if filter_contact == "Hanya yang Punya Kontak":
            filtered_leads = filtered_leads[filtered_leads['No. Telepon'] != 'Tidak ada']
        elif filter_contact == "Hanya yang Tanpa Kontak":
            filtered_leads = filtered_leads[filtered_leads['No. Telepon'] == 'Tidak ada']
            
        if filter_class:
            filtered_leads = filtered_leads[filtered_leads['Kelas_Reputasi'].isin(filter_class)]
            
        pd_st.write(f"Menampilkan **{len(filtered_leads)}** prospek yang cocok dengan kriteria filter Anda.")
        
        # Tampilkan DataFrame Hasil Filter
        cols_to_show = ['Nama Tempat', 'Rating', 'No. Telepon', 'Alamat', 'Website', 'Kelas_Reputasi']
        pd_st.dataframe(filtered_leads[cols_to_show], use_container_width=True)
        
        # Utilitas Ekspor Kustom berdasarkan Hasil Filter
        col_exp1, col_exp2, _ = pd_st.columns([2, 2, 4])
        
        csv_filtered = filtered_leads[cols_to_show].to_csv(index=False).encode('utf-8')
        col_exp1.download_button(
            "Ekspor CSV Terfilter", 
            data=csv_filtered, 
            file_name=f"leads_{keyword_safe}_filtered.csv", 
            mime="text/csv", 
            use_container_width=True
        )
        
        excel_filtered_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_filtered_buffer, engine='openpyxl') as writer:
            filtered_leads[cols_to_show].to_excel(writer, index=False, sheet_name='Filtered Leads')
        col_exp2.download_button(
            "Ekspor Excel Terfilter", 
            data=excel_filtered_buffer.getvalue(), 
            file_name=f"leads_{keyword_safe}_filtered.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
            use_container_width=True
        )

else:
    # State Awal Saat Pengguna Baru Saja Membuka Tautan SaaS Anda
    pd_st.info("Silakan tentukan kata kunci target di atas, lalu tekan tombol 'Mulai Scrape & Analisis' untuk memuat dashboard.")
