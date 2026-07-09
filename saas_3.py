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

# =============================================================================
# 1. DATABASE USER & KUOTA (SIMULASI BACKEND)
# =============================================================================
# Menggunakan session_state agar perubahan kuota oleh admin tidak hilang saat refresh halaman
if "user_db" not in pd_st.session_state:
    pd_st.session_state.user_db = {
        "demo": {"password": "demo", "quota": 3, "role": "demo"},
        "admin_saas": {"password": "adminsuper", "quota": 9999, "role": "admin"},
        "premium_user1": {"password": "password123", "quota": 10, "role": "subscriber"},
        "premium_user2": {"password": "password456", "quota": 20, "role": "subscriber"}
    }

# Inisialisasi status login pengguna
if "logged_in" not in pd_st.session_state:
    pd_st.session_state.logged_in = False
    pd_st.session_state.current_user = None
if "saas_df" not in pd_st.session_state:
    pd_st.session_state.saas_df = None
if "current_keyword" not in pd_st.session_state:
    pd_st.session_state.current_keyword = ""

# =============================================================================
# 2. HELPER FUNCTIONS & SCRAPER ENGINE
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
    async with async_playwright() as p:
        status_ui.text("Menginisialisasi sistem web browser virtual...")
        browser = await p.chromium.launch(headless=True) 
        page = await browser.new_page()
        
        search_url = f"https://www.google.com/maps/search/{keyword}/"
        status_ui.text(f"Mengirim query pencarian untuk: '{keyword}'...")
        await page.goto(search_url)
        
        try:
            await page.wait_for_selector('div[role="feed"]', timeout=10000)
        except Exception:
            await browser.close()
            return None
        
        status_ui.text("Membuka gulungan peta (Scrolling feed)...")
        for i in range(3): # Dibuat lebih cepat untuk demo/trial
            feed = await page.query_selector('div[role="feed"]')
            if feed:
                await feed.evaluate("element => element.scrollBy(0, 3000)")
                await page.wait_for_timeout(1000)
        
        place_elements = await page.query_selector_all('a[href*="/maps/place/"]')
        urls_to_scrape = []
        for el in place_elements:
            href = await el.get_attribute('href')
            if href and href not in urls_to_scrape: urls_to_scrape.append(href)
        
        total_urls = len(urls_to_scrape[:10]) # Batasi maks 10 data untuk efisiensi resource server
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
                rating_el = await page.query_selector('div.F7nice')
                if rating_el: rating = (await rating_el.inner_text()).replace("\n", " ")
                
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
# 3. INTERFACE HALAMAN LOGIN
# =============================================================================
if not pd_st.session_state.logged_in:
    pd_st.set_page_config(page_title="Login - SaaS Analytics", layout="centered")
    pd_st.title("Login Platform MarketSpy Analytics")
    
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
    # 4. HALAMAN UTAMA DASHBOARD (SETELAH LOGIN)
    # =============================================================================
    pd_st.set_page_config(page_title="SaaS Maps Analytics & Scraper", layout="wide")
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
        
    # --- PANEL ADMIN (Bisa Adjust Kuota & Buat Akun Baru) ---
    if user_info['role'] == 'admin':
        pd_st.sidebar.markdown("---")
        pd_st.sidebar.subheader("Panel Super Admin")
        
        # Form Tambah/Edit Akun Langganan
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

    # --- MAIN PAGE: AREA PENCARIAN CONTROLLER ---
    pd_st.title("MarketSpy & Analytics Platform")
    
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
                # POTONG KUOTA USER SETELAH BERHASIL SEARCH
                pd_st.session_state.user_db[current_user]['quota'] -= 1
                
                df_processed = preprocess_data(pd.DataFrame(raw_results))
                pd_st.session_state.saas_df = df_processed
                pd_st.session_state.current_keyword = input_keyword
                pd_st.success(f"Analisis Selesai! Kuota berkurang. Sisa Kuota Anda: {pd_st.session_state.user_db[current_user]['quota']} kali.")
                pd_st.rerun()
            else:
                pd_st.error("Pencarian gagal. Google Maps tidak mengembalikan hasil.")

    # =============================================================================
    # 5. DASHBOARD DATA INTERAKTIF RE-RENDER
    # =============================================================================
    if pd_st.session_state.saas_df is not None:
        df = pd_st.session_state.saas_df
        keyword_safe = pd_st.session_state.current_keyword.replace(" ", "_")
        
        # UTILITY EXPORT BUTTONS
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
                    folium.Marker(
                        location=[row['Latitude'], row['Longitude']],
                        popup=f"<b>{row['Nama Tempat']}</b><br>Rating: {row['Rating']}",
                        icon=folium.Icon(color=pin_color, icon='briefcase', prefix='fa')
                    ).add_to(marker_cluster)
                st_folium(m, width=1300, height=450)
            else:
                pd_st.error("Koordinat lokasi tidak terdeteksi.")

        # TAB 2: REPUTATION (SISTEM QC PERBAIKAN)
        with tab_reputation:
            pd_st.subheader("Metrik Analisis Reputasi & Kepuasan Konsumen")
            df_valid_rating = df.dropna(subset=['Rating_Murni'])
            bad_branches = df_valid_rating[(df_valid_rating['Rating_Murni'] <= 4.0) & (df_valid_rating['Rating_Murni'] > 0)]
            
            rep_col1, rep_col2, rep_col3 = pd_st.columns(3)
            rep_col1.metric("Rerata Rating Pasar", f"{df_valid_rating['Rating_Murni'].mean():.2f} / 5.0")
            rep_col2.metric("Review Terbanyak", f"{int(df['Total_Ulasan'].max())} Ulasan")
            rep_col3.metric("Butuh Evaluasi QC", f"{len(bad_branches)} Titik")
            
            g_layout1, g_layout2 = pd_st.columns([3, 2])
            with g_layout1:
                fig_hist = px.histogram(df_valid_rating, x="Rating_Murni", nbins=12, title="Distribusi Kesehatan Rating", color_discrete_sequence=['#10B981'])
                pd_st.plotly_chart(fig_hist, use_container_width=True)
            with g_layout2:
                fig_scat = px.scatter(df, x="Total_Ulasan", y="Rating_Murni", hover_name="Nama Tempat", title="Volume Review vs Kualitas", color_discrete_sequence=['#3B82F6'])
                pd_st.plotly_chart(fig_scat, use_container_width=True)
                
            pd_st.write("### Daftar Kategori Lampu Merah (Rating <= 4.0)")
            if not bad_branches.empty:
                pd_st.dataframe(bad_branches.sort_values(by='Rating_Murni')[['Nama Tempat', 'Rating', 'No. Telepon', 'Alamat']], use_container_width=True)
            else:
                pd_st.success("Tidak ada kategori dengan rating buruk (<= 4.0).")

        # TAB 3: DIGITAL READINESS
        with tab_digital:
            pd_st.subheader("Audit Penetrasi Infrastruktur Digital")
            has_website_count = len(df[df['Website'] != 'Belum punya'])
            fig_p1 = px.pie(names=["Miliki Website", "Belum Punya Website"], values=[has_website_count, len(df)-has_website_count], hole=0.4, color_discrete_sequence=['#2ECC71', '#E74C3C'])
            pd_st.plotly_chart(fig_p1)
            
            pd_st.write("### Hot Leads Generator")
            pd_st.dataframe(df[df['Website'] == 'Belum punya'][['Nama Tempat', 'No. Telepon', 'Alamat']], use_container_width=True)

        # TAB 4: BRAND CONSISTENCY
        with tab_brand:
            pd_st.subheader(" Audit Standar Nama")
            pd_st.dataframe(df[['Nama Tempat', 'Rating', 'No. Telepon', 'Alamat', 'Website']], use_container_width=True)
    else:
        pd_st.info("Silakan tentukan kata kunci target di atas, lalu tekan tombol 'Mulai Scrape & Analisis' untuk memuat dashboard.")
