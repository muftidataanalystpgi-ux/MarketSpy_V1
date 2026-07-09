import streamlit as pd_st
import asyncio
import nest_asyncio
from playwright.async_api import async_playwright
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
import re
import io
import os

# 1. KONFIGURASI HALAMAN (Wajib di awal script & hanya boleh dipanggil sekali)
pd_st.set_page_config(page_title="MarketSpy Analytics & Scraper", layout="wide")

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

# Mengizinkan nested event loops dari Playwright di dalam thread Streamlit
nest_asyncio.apply()

# =============================================================================
# 2. DATABASE USER & KUOTA (SIMULASI BACKEND)
# =============================================================================
if "user_db" not in pd_st.session_state:
    pd_st.session_state.user_db = {
        "demo": {"password": "demo", "quota": 3, "role": "demo"},
        "admin_saas": {"password": "adminsuper", "quota": 9999, "role": "admin"},
        "premium_user1": {"password": "password123", "quota": 10, "role": "subscriber"},
        "premium_user2": {"password": "password456", "quota": 20, "role": "subscriber"}
    }

if "logged_in" not in pd_st.session_state:
    pd_st.session_state.logged_in = False
    pd_st.session_state.current_user = None
if "saas_df" not in pd_st.session_state:
    pd_st.session_state.saas_df = None
if "current_keyword" not in pd_st.session_state:
    pd_st.session_state.current_keyword = ""

# =============================================================================
# 3. HELPER FUNCTIONS & SCRAPER ENGINE
# =============================================================================
def clean_text(text):
    if not text: return "Tidak terdeteksi"
    cleaned = re.sub(r'[^\x00-\x7F]+', '', text)
    return cleaned.strip()

def extract_lat_lng(url):
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match: return match.group(1), match.group(2)
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
    status_ui.text("Memeriksa kesiapan browser driver di server...")
    os.system("playwright install chromium")
    
    async with async_playwright() as p:
        status_ui.text("Menginisialisasi sistem web browser virtual...")
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        ) 
        
        # Sembunyikan identitas bot dengan User Agent Manusia asli
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
        for i in range(3):
            feed = await page.query_selector('div[role="feed"]')
            if feed:
                await feed.evaluate("element => element.scrollBy(0, 3000)")
                await page.wait_for_timeout(1000)
        
        place_elements = await page.query_selector_all('a[href*="/maps/place/"]')
        urls_to_scrape = []
        for el in place_elements:
            href = await el.get_attribute('href')
            if href and href not in urls_to_scrape: urls_to_scrape.append(href)
        
        total_urls = len(urls_to_scrape[:10])
        status_ui.text(f"Ditemukan {total_urls} lokasi potensial. Memulai ekstraksi...")
        
        extracted_data = []
        for index, target_url in enumerate(urls_to_scrape[:10]):
            try:
                status_ui.text(f"[Proses {index+1}/{total_urls}] Mengekstrak data...")
                await page.goto(target_url)
                try:
                    await page.wait_for_url(lambda url: "@" in url, timeout=3000)
                except:
                    await page.wait_for_timeout(500)
                
                latitude, longitude = extract_lat_lng(page.url)
                nama_el = await page.query_selector('h1')
                nama = clean_text(await nama_el.inner_text()) if nama_el else "Tanpa Nama"
                
                rating = "N/A"
                # Selektor tangguh berbasis text aria-label bintang
                rating_el = await page.query_selector('span[aria-label*="bintang"], span[aria-label*="stars"]')
                if rating_el: 
                    rating = await rating_el.get_attribute('aria-label')
                else:
                    rating_check = await page.query_selector('div.F7nice')
                    if rating_check: rating = (await rating_check.inner_text()).replace("\n", " ")
                
                alamat = "Tidak terdeteksi"
                address_el = await page.query_selector('button[data-item-id="address"]')
                if address_el: alamat = await address_el.inner_text()
                
                telepon = "Tidak ada"
                phone_el = await page.query_selector('button[data-item-id^="phone:tel:"]')
                if phone_el: telepon = await phone_el.inner_text()
                
                website = "Belum punya"
                web_el = await page.query_selector('a[data-item-id="authority"]')
                if web_el: website = await web_el.get_attribute('href') or "Belum punya"
                
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
# 4. INTERFACE HALAMAN LOGIN
# =============================================================================
if not pd_st.session_state.logged_in:
    _, login_col, _ = pd_st.columns([1, 2, 1])
    with login_col:
        pd_st.write("##")
        pd_st.markdown("""
            <div style="background: white; padding: 2rem; border-radius: 1rem; border: 1px solid #E2E8F0; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05);">
                <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem;">
                    <div style="height: 2.5rem; width: 2.5rem; background: #4F46E5; border-radius: 0.5rem; display: flex; align-items: center; justify-content: center; color: white; font-size: 1.25rem; font-weight: bold;">M</div>
                    <div>
                        <h2 style="margin: 0; font-size: 1.25rem;">MarketSpy Terminal</h2>
                        <span style="font-size: 0.75rem; color: #4F46E5; font-weight: 600; uppercase">Product Intelligence</span>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        with pd_st.form("login_form"):
            username_input = pd_st.text_input("Username").strip()
            password_input = pd_st.text_input("Password", type="password").strip()
            submit_login = pd_st.form_submit_button("Masuk Aplikasi", type="primary")
            
            if submit_login:
                db = pd_st.session_state.user_db
                if username_input in db and db[username_input]["password"] == password_input:
                    pd_st.session_state.logged_in = True
                    pd_st.session_state.current_user = username_input
                    pd_st.success("Login Berhasil! Mengalihkan...")
                    pd_st.rerun()
                else:
                    pd_st.error("Username atau Password salah. Silakan coba lagi.")
                    
        pd_st.info("Akun Akses Demo -> Username: demo | Password: demo")
    
else:
    # =============================================================================
    # 5. HALAMAN UTAMA DASHBOARD (SETELAH LOGIN)
    # =============================================================================
    current_user = pd_st.session_state.current_user
    user_info = pd_st.session_state.user_db[current_user]
    
    # --- SIDEBAR CONTROL & ADMIN PANEL ---
    pd_st.sidebar.title(f"👤 Akun: `{current_user}`")
    pd_st.sidebar.markdown(f"**Tipe Akun:** {user_info['role'].upper()}")
    pd_st.sidebar.markdown(f"**Sisa Kuota Cari:** `{user_info['quota']}` kali")
    
    if pd_st.sidebar.button("Logout 🚪", type="secondary"):
        pd_st.session_state.logged_in = False
        pd_st.session_state.current_user = None
        pd_st.session_state.saas_df = None
        pd_st.rerun()
        
    if user_info['role'] == 'admin':
        pd_st.sidebar.markdown("---")
        pd_st.sidebar.subheader("Panel Super Admin")
        
        with pd_st.sidebar.form("admin_panel"):
            pd_st.write("**Adjust / Buat Akun**")
            adm_user = pd_st.text_input("Username Baru/Lama").strip()
            adm_pass = pd_st.text_input("Password").strip()
            adm_quota = pd_st.number_input("Atur Jumlah Kuota", min_value=0, value=10)
            btn_save = pd_st.form_submit_button("Simpan Data Akun")
            
            if btn_save and adm_user:
                pd_st.session_state.user_db[adm_user] = {
                    "password": adm_pass if adm_pass else "12345",
                    "quota": adm_quota,
                    "role": "subscriber"
                }
                pd_st.sidebar.success(f"Akun `{adm_user}` diset ke {adm_quota}x cari!")
                pd_st.rerun()

    # --- MAIN PAGE: HEADER BANNER INDIGO ---
    pd_st.markdown("""
        <div style="background: white; padding: 1.5rem; border-radius: 0.75rem; border: 1px solid #E2E8F0; margin-bottom: 1.5rem; display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 1rem;">
                <div style="height: 2.5rem; width: 2.5rem; background: #4F46E5; border-radius: 0.5rem; display: flex; align-items: center; justify-content: center; color: white; font-size: 1.25rem; font-weight: bold;">M</div>
                <div>
                    <h2 style="margin: 0; font-size: 1.25rem; line-height: 1.2;">MarketSpy Analytics Terminal</h2>
                    <span style="font-size: 0.75rem; color: #4F46E5; font-weight: 600; text-transform: uppercase;">SaaS Live Engine</span>
                </div>
            </div>
            <div style="background: #ECFDF5; color: #059669; px: 3px; py: 1.5px; padding: 6px 12px; border-radius: 0.5rem; font-size: 0.75rem; font-weight: 600; display: flex; align-items: center; gap: 0.5rem;">
                <span style="height: 0.5rem; width: 0.5rem; background: #10B981; border-radius: 50%;"></span> API Status: Active
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    with pd_st.container(border=True):
        col_search, col_action = pd_st.columns([4, 1])
        with col_search:
            input_keyword = pd_st.text_input("Masukkan Kata Kunci Pasar & Lokasi Target", placeholder="Contoh: seblak bandung, raja susu tegal").strip()
        with col_action:
            pd_st.write("##") 
            start_button = pd_st.button("Mulai Scrape & Analisis", type="primary", use_container_width=True)

    if start_button:
        if not input_keyword:
            pd_st.error("Gagal! Kata kunci pencarian tidak boleh kosong.")
        elif user_info['quota'] <= 0:
            pd_st.error("Kuota pencarian akun Anda sudah habis! Silakan hubungi admin untuk memperpanjang langganan.")
        else:
            status_placeholder = pd_st.empty()
            with pd_st.spinner("Mengaktifkan cloud worker engine..."):
                raw_results = asyncio.run(run_google_maps_scraper(input_keyword, status_placeholder))
            
            status_placeholder.empty()
            
            if raw_results:
                pd_st.session_state.user_db[current_user]['quota'] -= 1
                df_processed = preprocess_data(pd.DataFrame(raw_results))
                pd_st.session_state.saas_df = df_processed
                pd_st.session_state.current_keyword = input_keyword
                pd_st.success(f"Analisis Selesai! Sisa Kuota Anda: {pd_st.session_state.user_db[current_user]['quota']} kali.")
                pd_st.rerun()
            else:
                pd_st.error("Pencarian gagal. Google Maps mendeteksi bot atau tidak mengembalikan hasil. Silakan coba lagi.")

    # =============================================================================
    # 6. DASHBOARD DATA INTERAKTIF RE-RENDER
    # =============================================================================
    if pd_st.session_state.saas_df is not None:
        df = pd_st.session_state.saas_df
        keyword_safe = pd_st.session_state.current_keyword.replace(" ", "_")
        
        col_dl1, col_dl2, _ = pd_st.columns([1.5, 1.5, 5])
        csv_buffer = df.to_csv(index=False).encode('utf-8')
        col_dl1.download_button("Unduh File CSV", data=csv_buffer, file_name=f"saas_{keyword_safe}.csv", mime="text/csv", use_container_width=True)
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Data Analytics')
        col_dl2.download_button("Unduh File Excel", data=excel_buffer.getvalue(), file_name=f"saas_{keyword_safe}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

        tab_geo, tab_reputation, tab_digital, tab_brand = pd_st.tabs([
            "Geospatial Analytics", "Reputation Analytics", "Digital Readiness & Audit", "Brand Consistency"
        ])
        
        # TAB 1: GEOSPATIAL
        with tab_geo:
            pd_st.subheader("Analisis Pemetaan Spasial Komersial")
            df_geo = df.dropna(subset=['Latitude', 'Longitude'])
            if not df_geo.empty:
                m = folium.Map(location=[df_geo['Latitude'].mean(), df_geo['Longitude'].mean()], zoom_start=11)
                marker_cluster = MarkerCluster().add_to(m)
                for _, row in df_geo.iterrows():
                    r = row['Rating_Murni']
                    pin_color = 'green' if r >= 4.5 else 'orange' if r >= 4.0 else 'red' if r < 4.0 else 'blue'
                    
                    popup_box = f"""
                    <div style='font-family: "Segoe UI", Arial, sans-serif; min-width: 220px; line-height: 1.5;'>
                        <div style='border-top: 4px solid #4F46E5; margin-bottom: 6px;'></div>
                        <h4 style='margin:0 0 4px 0; color:#0F172A; font-size:13px;'>{row['Nama Tempat']}</h4>
                        <span style='color:#64748B;'>⭐ Rating:</span> <strong>{row['Rating']}</strong><br>
                        <span style='color:#64748B;'>📞 Telp:</span> <strong>{row['No. Telepon']}</strong>
                    </div>
                    """
                    folium.Marker(
                        location=[row['Latitude'], row['Longitude']],
                        popup=popup_box,
                        icon=folium.Icon(color=pin_color, icon='briefcase', prefix='fa')
                    ).add_to(marker_cluster)
                st_folium(m, width=1300, height=450)
            else:
                pd_st.error("Koordinat lokasi tidak terdeteksi.")

        # TAB 2: REPUTATION (KPI Cards Bergaya MarketSpy HTML)
        with tab_reputation:
            pd_st.write("##")
            df_valid_rating = df.dropna(subset=['Rating_Murni'])
            bad_branches = df_valid_rating[(df_valid_rating['Rating_Murni'] <= 4.0) & (df_valid_rating['Rating_Murni'] > 0)]
            
            avg_rating = f"{df_valid_rating['Rating_Murni'].mean():.2f}"
            max_reviews = int(df['Total_Ulasan'].max())
            total_bad = len(bad_branches)

            # SUNTIK KPI CARDS DARI HTML
            m_col1, m_col2, m_col3 = pd_st.columns(3)
            with m_col1:
                pd_st.markdown(f"""
                    <div style="background: white; padding: 1.5rem; border-radius: 0.75rem; border: 1px solid #E2E8F0; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 2px rgb(0 0 0 / 0.05);">
                        <div>
                            <span style="font-size: 0.75rem; font-weight: bold; color: #94A3B8; text-transform: uppercase; tracking-wider">Rerata Rating Pasar</span>
                            <h3 style="margin: 0.25rem 0 0 0; font-size: 1.5rem; color: #1E293B;">{avg_rating} <span style="font-size: 0.875rem; color: #94A3B8; font-weight: normal;">/ 5.0</span></h3>
                        </div>
                        <div style="height: 2.5rem; width: 2.5rem; background: #EEF2FF; color: #4F46E5; border-radius: 0.5rem; display: flex; align-items: center; justify-content: center; font-size: 1.25rem;"><i class="fa-solid fa-star"></i></div>
                    </div>
                """, unsafe_allow_html=True)

            with m_col2:
                pd_st.markdown(f"""
                    <div style="background: white; padding: 1.5rem; border-radius: 0.75rem; border: 1px solid #E2E8F0; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 2px rgb(0 0 0 / 0.05);">
                        <div>
                            <span style="font-size: 0.75rem; font-weight: bold; color: #94A3B8; text-transform: uppercase; tracking-wider">Volume Review Terbanyak</span>
                            <h3 style="margin: 0.25rem 0 0 0; font-size: 1.5rem; color: #1E293B;">{max_reviews} <span style="font-size: 0.875rem; color: #94A3B8; font-weight: normal;">Ulasan</span></h3>
                        </div>
                        <div style="height: 2.5rem; width: 2.5rem; background: #ECFDF5; color: #10B981; border-radius: 0.5rem; display: flex; align-items: center; justify-content: center; font-size: 1.25rem;"><i class="fa-solid fa-list-check"></i></div>
                    </div>
                """, unsafe_allow_html=True)

            with m_col3:
                pd_st.markdown(f"""
                    <div style="background: white; padding: 1.5rem; border-radius: 0.75rem; border: 1px solid #E2E8F0; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 2px rgb(0 0 0 / 0.05);">
                        <div>
                            <span style="font-size: 0.75rem; font-weight: bold; color: #94A3B8; text-transform: uppercase; tracking-wider">Cabang Evaluasi QC</span>
                            <h3 style="margin: 0.25rem 0 0 0; font-size: 1.5rem; color: #EF4444;">{total_bad} <span style="font-size: 0.875rem; color: #94A3B8; font-weight: normal;">Titik</span></h3>
                        </div>
                        <div style="height: 2.5rem; width: 2.5rem; background: #FEF2F2; color: #EF4444; border-radius: 0.5rem; display: flex; align-items: center; justify-content: center; font-size: 1.25rem;"><i class="fa-solid fa-triangle-exclamation"></i></div>
                    </div>
                """, unsafe_allow_html=True)
            
            pd_st.write("##")
            g_layout1, g_layout2 = pd_st.columns([3, 2])
            with g_layout1:
                fig_hist = px.histogram(df_valid_rating, x="Rating_Murni", nbins=12, title="Distribusi Kesehatan Rating", color_discrete_sequence=['#4F46E5'])
                pd_st.plotly_chart(fig_hist, use_container_width=True)
            with g_layout2:
                fig_scat = px.scatter(df, x="Total_Ulasan", y="Rating_Murni", hover_name="Nama Tempat", title="Volume Review vs Kualitas", color_discrete_sequence=['#3B82F6'])
                pd_st.plotly_chart(fig_scat, use_container_width=True)
                
            pd_st.write("### Daftar Cabang Kategori Lampu Merah (Rating <= 4.0)")
            if not bad_branches.empty:
                pd_st.dataframe(bad_branches.sort_values(by='Rating_Murni')[['Nama Tempat', 'Rating', 'No. Telepon', 'Alamat']], use_container_width=True)
            else:
                pd_st.success("🎉 Tidak ada cabang dengan rating buruk (<= 4.0).")

        # TAB 3: DIGITAL READINESS
        with tab_digital:
            pd_st.subheader("Audit Penetrasi Infrastruktur Digital")
            has_website_count = len(df[df['Website'] != 'Belum punya'])
            fig_p1 = px.pie(names=["Miliki Website", "Belum Punya Website"], values=[has_website_count, len(df)-has_website_count], hole=0.4, color_discrete_sequence=['#10B981', '#EF4444'])
            pd_st.plotly_chart(fig_p1)
            
            pd_st.write("### Hot Leads Generator")
            pd_st.dataframe(df[df['Website'] == 'Belum punya'][['Nama Tempat', 'No. Telepon', 'Alamat']], use_container_width=True)

        # TAB 4: BRAND CONSISTENCY
        with tab_brand:
            pd_st.subheader("Audit Standar Nama")
            pd_st.dataframe(df[['Nama Tempat', 'Rating', 'No. Telepon', 'Alamat', 'Website']], use_container_width=True)
    else:
        pd_st.info("Silakan tentukan kata kunci target di atas, lalu tekan tombol 'Mulai Scrape & Analisis' untuk memuat dashboard.")
