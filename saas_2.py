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
import os # <-- Tambahkan ini jika belum ada

# Trik Otomatisasi Instalasi Biner Playwright di Server Cloud
if not os.path.exists("/home/adminuser/.cache/ms-playwright"):
    os.system("playwright install chromium")
# =============================================================================
# CONFIGURATION & HEADER (UPGRADED WITH PREMIUM BLUE SAAS STYLE)
# =============================================================================
pd_st.set_page_config(page_title="MarketSpy", layout="wide")

# SUNTIK DESIGN ULTRA-PREMIUM SAAS (Identik dengan elemen marketspy_app.html)
pd_st.markdown("""
    <!-- Load FontAwesome Icons & Premium Fonts -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    
    <style>
        /* Desain Latar Belakang & Tipografi Global */
        html, body, [data-testid="stAppViewContainer"] {
            font-family: 'Inter', sans-serif;
            background-color: #F8FAFC !important; /* bg-slate-50 */
        }
        h1, h2, h3, h4 {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-weight: 700 !important;
            color: #0F172A !important; /* text-slate-900 */
        }
        
        /* Custom Scrollbar Halus khas SaaS Modern */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #F1F5F9; }
        ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #94A3B8; }
        
        /* Modifikasi Tombol Utama Streamlit (Warna Indigo/Blue Premium) */
        div.stButton > button:first-child {
            background-color: #4F46E5 !important; /* Indigo 600 */
            color: white !important;
            border-radius: 0.75rem !important; /* rounded-xl */
            border: none !important;
            font-weight: 600 !important;
            padding: 0.625rem 1.25rem !important;
            box-shadow: 0 4px 6px -1px rgb(79 70 229 / 0.1), 0 2px 4px -2px rgb(79 70 229 / 0.1) !important;
            transition: all 0.2s;
        }
        div.stButton > button:first-child:hover {
            background-color: #4338CA !important; /* Indigo 700 */
            transform: translateY(-1px);
        }
    </style>
""", unsafe_allow_html=True)

# BANNER UTAMA INDIGO PREMIUM
pd_st.markdown("""
    <div style="background: white; padding: 1.5rem; border-radius: 0.75rem; border: 1px solid #E2E8F0; margin-bottom: 1.5rem; display: flex; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 1rem;">
            <div style="height: 2.5rem; width: 2.5rem; background: #4F46E5; border-radius: 0.5rem; display: flex; align-items: center; justify-content: center; color: white; font-size: 1.25rem; font-weight: bold;">M</div>
            <div>
                <h2 style="margin: 0; font-size: 1.25rem; line-height: 1.2;">MarketSpy Analytics Terminal</h2>
                <span style="font-size: 0.75rem; color: #4F46E5; font-weight: 600; text-transform: uppercase;">SaaS Live Engine</span>
            </div>
        </div>
        <div style="background: #ECFDF5; color: #059669; padding: 6px 12px; border-radius: 0.5rem; font-size: 0.75rem; font-weight: 600; display: flex; align-items: center; gap: 0.5rem;">
            <span style="height: 0.5rem; width: 0.5rem; background: #10B981; border-radius: 50%;"></span> API Status: Active
        </div>
    </div>
""", unsafe_allow_html=True)

# Initialize session state agar data hasil scraping tidak hilang saat berpindah tab/interaksi
if "saas_df" not in pd_st.session_state:
    pd_st.session_state.saas_df = None
if "current_keyword" not in pd_st.session_state:
    pd_st.session_state.current_keyword = ""

# =============================================================================
# HELPER FUNCTIONS & SCRAPER ENGINE (BACKEND ASLI)
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
        data['Rating_Murni'] = None
        data['Total_Ulasan'] = 0
        
    data['Latitude'] = pd.to_numeric(data['Latitude'], errors='coerce')
    data['Longitude'] = pd.to_numeric(data['Longitude'], errors='coerce')
    return data

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
            await page.wait_for_selector('div[role="feed"], a[href*="/maps/place/"]', timeout=15000)
        except Exception:
            await browser.close()
            return None
        
        status_ui.text("Membuka gulungan peta (Scrolling feed)...")
        for i in range(40):  # Dioptimalkan 5 kali scroll demi kecepatan performa respons SaaS
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
                rating_el = await page.query_selector('span[aria-label*="bintang"], span[aria-label*="stars"]')
                if rating_el: 
                    rating = await rating_el.get_attribute('aria-label')
                else:
                    rating_check = await page.query_selector('div.F7nice')
                    if rating_check: rating = (await rating_check.inner_text()).replace("\n", " ")
                
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
        input_keyword = pd_st.text_input("Masukkan Kata Kunci Pasar & Lokasi Target", placeholder="Contoh: raja gadai tegal, pandai gadai, seblak bandung").strip()
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
    
    # --- UTILITY EXPORT BUTTONS ---
    col_dl1, col_dl2, _ = pd_st.columns([1.5, 1.5, 5])
    
    # CSV Export
    csv_buffer = df.to_csv(index=False).encode('utf-8')
    col_dl1.download_button("Unduh File CSV", data=csv_buffer, file_name=f"saas_{keyword_safe}.csv", mime="text/csv", use_container_width=True)
    
    # Excel Export (In-Memory Buffer)
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Data Analytics')
    col_dl2.download_button("Unduh File Excel", data=excel_buffer.getvalue(), file_name=f"saas_{keyword_safe}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    # --- TABS LAYOUT ---
    tab_geo, tab_reputation, tab_digital, tab_brand = pd_st.tabs([
        "Geospatial Analytics", 
        "Reputation Analytics", 
        "Digital Readiness & Audit", 
        "Brand Consistency"
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
                # Pewarnaan dinamis
                pin_color = 'green' if r >= 4.5 else 'orange' if r >= 4.0 else 'red' if r < 4.0 else 'blue'
                
                popup_box = f"""
                <div style='font-family: "Segoe UI", Arial, sans-serif; min-width: 220px; line-height: 1.5;'>
                    <div style='border-top: 4px solid #4F46E5; margin-bottom: 6px;'></div>
                    <h4 style='margin:0 0 4px 0; color:#0F172A; font-size:13px;'>{row['Nama Tempat']}</h4>
                    <span style='color:#64748B;'>⭐ Rating:</span> <strong>{row['Rating']}</strong><br>
                    <span style='color:#64748B;'>📞 Telepon:</span> <strong>{row['No. Telepon']}</strong><br>
                    <span style='color:#64748B;'>📍 Alamat:</span> <span style='color:#334155; font-size:11px;'>{row['Alamat']}</span>
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
    # TAB 2: REPUTATION ANALYTICS (UPGRADED WITH HTML SAAS CARDS)
    # -------------------------------------------------------------------------
    with tab_reputation:
        pd_st.write("##")
        
        # Filter ketat: Harus berupa angka, tidak boleh NaN, dan berada di rentang 0.1 s/d 4.0
        df_valid_rating = df.dropna(subset=['Rating_Murni'])
        bad_branches = df_valid_rating[(df_valid_rating['Rating_Murni'] <= 4.0) & (df_valid_rating['Rating_Murni'] > 0)]
        
        avg_rating = f"{df_valid_rating['Rating_Murni'].mean():.2f}"
        max_reviews = int(df['Total_Ulasan'].max())
        total_bad = len(bad_branches)

        # SUNTIK METRIK KPI CARDS DESIGN DARI HTML
        rep_col1, rep_col2, rep_col3 = pd_st.columns(3)
        with rep_col1:
            pd_st.markdown(f"""
                <div style="background: white; padding: 1.5rem; border-radius: 0.75rem; border: 1px solid #E2E8F0; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 2px rgb(0 0 0 / 0.05);">
                    <div>
                        <span style="font-size: 0.75rem; font-weight: bold; color: #94A3B8; text-transform: uppercase;">Rerata Rating Pasar</span>
                        <h3 style="margin: 0.25rem 0 0 0; font-size: 1.5rem; color: #1E293B;">{avg_rating} <span style="font-size: 0.875rem; color: #94A3B8; font-weight: normal;">/ 5.0</span></h3>
                    </div>
                    <div style="height: 2.5rem; width: 2.5rem; background: #EEF2FF; color: #4F46E5; border-radius: 0.5rem; display: flex; align-items: center; justify-content: center; font-size: 1.25rem;"><i class="fa-solid fa-star"></i></div>
                </div>
            """, unsafe_allow_html=True)

        with rep_col2:
            pd_st.markdown(f"""
                <div style="background: white; padding: 1.5rem; border-radius: 0.75rem; border: 1px solid #E2E8F0; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 2px rgb(0 0 0 / 0.05);">
                    <div>
                        <span style="font-size: 0.75rem; font-weight: bold; color: #94A3B8; text-transform: uppercase;">Review Terbanyak (Popularitas)</span>
                        <h3 style="margin: 0.25rem 0 0 0; font-size: 1.5rem; color: #1E293B;">{max_reviews} <span style="font-size: 0.875rem; color: #94A3B8; font-weight: normal;">Ulasan</span></h3>
                    </div>
                    <div style="height: 2.5rem; width: 2.5rem; background: #ECFDF5; color: #10B981; border-radius: 0.5rem; display: flex; align-items: center; justify-content: center; font-size: 1.25rem;"><i class="fa-solid fa-list-check"></i></div>
                </div>
            """, unsafe_allow_html=True)

        with rep_col3:
            pd_st.markdown(f"""
                <div style="background: white; padding: 1.5rem; border-radius: 0.75rem; border: 1px solid #E2E8F0; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 2px rgb(0 0 0 / 0.05);">
                    <div>
                        <span style="font-size: 0.75rem; font-weight: bold; color: #94A3B8; text-transform: uppercase;">Butuh Evaluasi QC (Rating <= 4.0)</span>
                        <h3 style="margin: 0.25rem 0 0 0; font-size: 1.5rem; color: #EF4444;">{total_bad} <span style="font-size: 0.875rem; color: #94A3B8; font-weight: normal;">Titik</span></h3>
                    </div>
                    <div style="height: 2.5rem; width: 2.5rem; background: #FEF2F2; color: #EF4444; border-radius: 0.5rem; display: flex; align-items: center; justify-content: center; font-size: 1.25rem;"><i class="fa-solid fa-triangle-exclamation"></i></div>
                </div>
            """, unsafe_allow_html=True)
        
        pd_st.write("##")
        g_layout1, g_layout2 = pd_st.columns([3, 2])
        with g_layout1:
            fig_hist = px.histogram(df_valid_rating, x="Rating_Murni", nbins=12,
                                    title="Distribusi Kesehatan Rating Kompetitor",
                                    labels={'Rating_Murni': 'Skala Bintang Toko'},
                                    color_discrete_sequence=['#4F46E5']) # Disesuaikan ke Indigo
            pd_st.plotly_chart(fig_hist, use_container_width=True)
        with g_layout2:
            fig_scat = px.scatter(df, x="Total_Ulasan", y="Rating_Murni", hover_name="Nama Tempat",
                                  title="Matriks Korelasi Volume Review vs Kualitas Toko",
                                  labels={'Total_Ulasan': 'Jumlah Total Review', 'Rating_Murni': 'Rating'},
                                  color_discrete_sequence=['#3B82F6']) # Disesuaikan ke Blue
            pd_st.plotly_chart(fig_scat, use_container_width=True)
            
        pd_st.write("### Daftar Kategori Lampu Merah (Rating <= 4.0)")
        
        # Menampilkan data yang sudah terfilter dengan aman & berurutan dari rating terendah
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
                            color_discrete_sequence=['#10B981', '#EF4444']) # Emerald & Coral Red
            pd_st.plotly_chart(fig_p1, use_container_width=True)
        with d_col2:
            fig_p2 = px.pie(names=["Miliki Kontak", "Tidak Ada Kontak"], 
                            values=[has_phone_count, total_items - has_phone_count], 
                            title="Aksesibilitas Komunikasi (Telepon)", hole=0.4,
                            color_discrete_sequence=['#3B82F6', '#CBD5E1']) # Blue Slate
            pd_st.plotly_chart(fig_p2, use_container_width=True)
            
        pd_st.write("### Hot Leads Generator (Target Prospek Prioritas Utama)")
        pd_st.warning("Daftar di bawah mengekstrak badan usaha yang belum mengoptimalkan website. Sangat disarankan untuk target penetrasi agensi pemasaran/pembuatan software.")
        leads_df = df[df['Website'] == 'Belum punya'][['Nama Tempat', 'No. Telepon', 'Alamat']]
        pd_st.dataframe(leads_df, use_container_width=True)

    # -------------------------------------------------------------------------
    # TAB 4: BRAND CONSISTENCY
    # -------------------------------------------------------------------------
    with tab_brand:
        pd_st.subheader("Audit Standardisasi & Konsistensi Identitas Brand")
        
        # Ekstraksi Token Kata Terbanyak untuk Analisis Klaster Merek
        text_stream = " ".join(df['Nama Tempat'].astype(str)).lower()
        cleaned_words = [w for w in text_stream.split() if len(w) > 3 and w not in ['dan', 'yang', 'dengan', 'toko', 'kedai']]
        word_freq = pd.Series(cleaned_words).value_counts().head(10).reset_index()
        word_freq.columns = ['Token Kata', 'Frekuensi Pemakaian']
        
        b_col1, b_col2 = pd_st.columns([2, 3])
        with b_col1:
            pd_st.write("#### Top Keyword Dominan Pada Nama")
            pd_st.dataframe(word_freq, use_container_width=True)
        with b_col2:
            fig_words = px.bar(word_freq, x="Frekuensi Pemakaian", y="Token Kata", orientation='h',
                               title="Pola Kata Kunci Nama di Lapangan", color="Frekuensi Pemakaian",
                               color_continuous_scale=px.colors.sequential.Blues) # Disesuaikan ke Gradasi Biru
            pd_st.plotly_chart(fig_words, use_container_width=True)
            
        pd_st.write("### Master Database Hasil Ekstraksi Lapangan")
        pd_st.dataframe(df[['Nama Tempat', 'Rating', 'No. Telepon', 'Alamat', 'Website']], use_container_width=True)

else:
    # State Awal Saat Pengguna Baru Saja Membuka Tautan SaaS Anda
    pd_st.info("Silakan tentukan kata kunci target di atas, lalu tekan tombol 'Mulai Scrape & Analisis' untuk memuat dashboard.")
