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
pd_st.markdown("Jalankan pencarian kompetitor, kumpulkan prospek penjualan (*leads*), "
              "dan analisis data pasar secara *real-time* dalam satu ekosistem digital.")

# Initialize session state agar data hasil scraping tidak hilang saat berpindah tab/interaksi
if "saas_df" not in pd_st.session_state:
    pd_st.session_state.saas_df = None
if "current_keyword" not in pd_st.session_state:
    pd_st.session_state.current_keyword = ""

# =============================================================================
# HELPER FUNCTIONS & CLEANING
# =============================================================================
def clean_text(text):
    if not text:
        return "N/A"
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_lat_lng(url):
    """Mengekstrak nilai Latitude dan Longitude dari URL Google Maps secara presisi."""
    try:
        match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
        if match:
            return float(match.group(1)), float(match.group(2))
    except Exception:
        pass
    return "N/A", "N/A"

def categorize_reputation(rating_str):
    """Mengkategorikan tempat berdasarkan rating numeriknya."""
    try:
        match = re.search(r'(\d+[\.,]\d+|\d+)', rating_str)
        if match:
            val = float(match.group(1).replace(',', '.'))
            if val >= 4.5: return "Reputasi Tinggi (Sangat Bagus)"
            elif val >= 3.5: return "Reputasi Sedang"
            else: return "Reputasi Rendah / Perlu Evaluasi"
    except Exception:
        pass
    return "Tidak Ada Data Rating"

# =============================================================================
# CORE ENGINE: PLAYWRIGHT GOOGLE MAPS SCRAPER (DEPTH & PRECISION)
# =============================================================================
async def run_google_maps_scraper(keyword, status_ui):
    async with async_playwright() as p:
        status_ui.text("Menginisialisasi sistem web browser virtual...")
        browser = await p.chromium.launch(
            headless=True, 
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        search_url = f"https://www.google.com/maps/search/{keyword}/"
        status_ui.text(f"Mengirim query pencarian untuk: '{keyword}'...")
        await page.goto(search_url)
        
        try:
            await page.wait_for_selector('div[role="feed"]', timeout=15000)
        except Exception:
            await browser.close()
            return None

        status_ui.text("Membuka gulungan peta (Scrolling tanpa batas statis untuk hasil maksimal)...")
        
        feed = await page.query_selector('div[role="feed"]')
        urls_to_scrape = []
        
        if feed:
            prev_len = 0
            same_count = 0
            while True:
                # Scroll ke bawah pada container feed dengan jangkauan lebih dalam
                await feed.evaluate("element => element.scrollBy(0, 8000)")
                await page.wait_for_timeout(2500) # Waktu tunggu render stabil agar presisi data terjaga
                
                # Ekstrak link secara berkala agar tidak hilang dari memori DOM browser saat di-scroll
                place_elements = await page.query_selector_all('a[href*="/maps/place/"]')
                for el in place_elements:
                    href = await el.get_attribute('href')
                    if href and href not in urls_to_scrape:
                        urls_to_scrape.append(href)
                
                current_len = len(urls_to_scrape)
                status_ui.text(f"Menjaring leads potensial... Terdeteksi sementara: {current_len} tempat.")
                
                # Cek penanda resmi jika Google Maps sudah mentok ke bawah
                source_content = await page.content()
                if "Anda telah mencapai akhir daftar" in source_content or "You've reached the end of the list" in source_content:
                    break
                
                # Pengaman putaran loop tak terbatas jika data memang sudah habis
                if current_len == prev_len:
                    same_count += 1
                    if same_count >= 5: 
                        break
                else:
                    same_count = 0
                
                prev_len = current_len

        total_urls = len(urls_to_scrape)
        status_ui.text(f"Total ditemukan {total_urls} titik presisi. Memulai ekstraksi detail mendalam...")
        
        extracted_data = []
        for index, target_url in enumerate(urls_to_scrape):
            try:
                status_ui.text(f"[Proses Ekstraksi {index+1}/{total_urls}] Mengamankan data...")
                await page.goto(target_url)
                
                # Menunggu perubahan koordinat URL peta dengan batas toleransi 7 detik (Sangat Presisi)
                try:
                    await page.wait_for_url(lambda url: "@" in url, timeout=7000)
                except:
                    await page.wait_for_timeout(1500)
                
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
                    "Nama Tempat": nama,
                    "Rating": clean_text(rating),
                    "No. Telepon": clean_text(telepon),
                    "Alamat": clean_text(alamat),
                    "Website": website,
                    "Latitude": latitude,
                    "Longitude": longitude
                })
            except Exception:
                continue
                
        await browser.close()
        return extracted_data

# =============================================================================
# USER INTERFACE - CONTROLS & SIDEBAR
# =============================================================================
pd_st.sidebar.header("Kontrol Spy & Scraper")
input_keyword = pd_st.sidebar.text_input("Kata Kunci Pencarian (contoh: 'Cafe Jakarta Selatan')", "")

if pd_st.sidebar.button("Mulai Scrape Data", type="primary"):
    if input_keyword.strip() == "":
        pd_st.sidebar.error("Silakan masukkan kata kunci terlebih dahulu!")
    else:
        status_box = pd_st.empty()
        raw_results = asyncio.run(run_google_maps_scraper(input_keyword, status_box))
        
        if raw_results:
            df_new = pd.DataFrame(raw_results)
            df_new['Kelas_Reputasi'] = df_new['Rating'].apply(categorize_reputation)
            
            pd_st.session_state.saas_df = df_new
            pd_st.session_state.current_keyword = input_keyword
            status_box.success(f"Berhasil mengumpulkan {len(df_new)} data untuk kata kunci '{input_keyword}'!")
        else:
            status_box.error("Gagal mendapatkan data atau selektor Maps berubah. Coba kata kunci lain.")

# =============================================================================
# MAIN DASHBOARD WORKSPACE
# =============================================================================
if pd_st.session_state.saas_df is not None:
    leads_df = pd_st.session_state.saas_df
    
    # Pembuatan Tab untuk Analisis Mendalam
    tab_data, tab_analytics, tab_mapping = pd_st.tabs(["📋 Data Leads & Prospek", "📊 Analitik Pasar", "📍 Pemetaan Lokasi"])
    
    # -------------------------------------------------------------------------
    # TAB 1: DATA LEADS & PROSPEK
    # -------------------------------------------------------------------------
    with tab_data:
        pd_st.subheader(f"Daftar Prospek Bisnis: {pd_st.session_state.current_keyword}")
        
        col_f1, col_f2 = pd_st.columns(2)
        with col_f1:
            filter_reputasi = pd_st.multiselect("Filter Berdasarkan Kelas Reputasi", 
                                                options=leads_df['Kelas_Reputasi'].unique(),
                                                default=leads_df['Kelas_Reputasi'].unique())
        with col_f2:
            search_name = pd_st.text_input("Cari Nama Tempat Tertentu", "")
            
        filtered_leads = leads_df[leads_df['Kelas_Reputasi'].isin(filter_reputasi)]
        if search_name:
            filtered_leads = filtered_leads[filtered_leads['Nama Tempat'].str.contains(search_name, case=False, na=False)]
            
        # Menampilkan DataFrame dengan Kolom Baru + Koordinat Presisi
        cols_to_show = ['Nama Tempat', 'Rating', 'No. Telepon', 'Alamat', 'Website', 'Kelas_Reputasi', 'Latitude', 'Longitude']
        pd_st.dataframe(filtered_leads[cols_to_show], use_container_width=True)
        
        pd_st.markdown("### 📥 Ekspor Hasil Pencarian")
        col_exp1, col_exp2 = pd_st.columns(2)
        
        # Ekspor CSV
        csv_buffer = io.StringIO()
        filtered_leads[cols_to_show].to_csv(csv_buffer, index=False)
        with col_exp1:
            pd_st.download_button(
                label="Ekspor CSV Terfilter",
                data=csv_buffer.getvalue(),
                file_name=f"Leads_{pd_st.session_state.current_keyword.replace(' ', '_')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
        # Ekspor Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            filtered_leads[cols_to_show].to_excel(writer, index=False, sheet_name='Leads Data')
        with col_exp2:
            pd_st.download_button(
                label="Ekspor Excel Terfilter",
                data=excel_buffer.getvalue(),
                file_name=f"Leads_{pd_st.session_state.current_keyword.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    # -------------------------------------------------------------------------
    # TAB 2: ANALITIK PASAR (MARKET ANALYTICS)
    # -------------------------------------------------------------------------
    with tab_analytics:
        pd_st.subheader("Analisis Distribusi Pasar & Reputasi Kompetitor")
        
        col_a1, col_a2 = pd_st.columns(2)
        
        with col_a1:
            reputation_counts = leads_df['Kelas_Reputasi'].value_counts().reset_index()
            reputation_counts.columns = ['Kelas_Reputasi', 'Jumlah']
            fig_pie = px.pie(reputation_counts, values='Jumlah', names='Kelas_Reputasi', 
                             title="Persentase Pangsa Reputasi Pasar",
                             color_discrete_sequence=px.colors.sequential.RdBu)
            pd_st.plotly_chart(fig_pie, use_container_width=True)
            
        with col_a2:
            leads_df['Status_Digital'] = leads_df['Website'].apply(lambda x: "Punya Website" if "http" in str(x) else "Belum Punya Website")
            digital_counts = leads_df['Status_Digital'].value_counts().reset_index()
            digital_counts.columns = ['Status_Digital', 'Total']
            fig_bar = px.bar(digital_counts, x='Status_Digital', y='Total', 
                             title="Tingkat Kematangan Digital (Saturasi Website)",
                             text='Total', color='Status_Digital',
                             color_discrete_map={"Punya Website": "#2ECC71", "Belum Punya Website": "#E74C3C"})
            pd_st.plotly_chart(fig_bar, use_container_width=True)

    # -------------------------------------------------------------------------
    # TAB 3: PEMETAAN LOKASI (GEOSPATIAL MAPPING)
    # -------------------------------------------------------------------------
    with tab_mapping:
        pd_st.subheader("Peta Persebaran Lokasi Kompetitor Terdeteksi")
        pd_st.markdown("Memetakan koordinat latitude dan longitude secara akurat menggunakan cluster marker.")
        
        map_df = leads_df[(leads_df['Latitude'] != "N/A") & (leads_df['Longitude'] != "N/A")].copy()
        
        if not map_df.empty:
            center_lat = map_df['Latitude'].astype(float).mean()
            center_lng = map_df['Longitude'].astype(float).mean()
            
            m = folium.Map(location=[center_lat, center_lng], zoom_start=12)
            marker_cluster = MarkerCluster().add_to(m)
            
            for _, row in map_df.iterrows():
                popup_content = f"""
                <div style='font-family: Arial, sans-serif; width: 200px;'>
                    <h5 style='margin:0 0 5px 0; color:#2C3E50;'>{row['Nama Tempat']}</h5>
                    <b>Rating:</b> {row['Rating']}<br>
                    <b>Telepon:</b> {row['No. Telepon']}<br>
                    <b>Website:</b> <a href='{row['Website']}' target='_blank'>Kunjungi</a><br>
                    <b>Reputasi:</b> {row['Kelas_Reputasi']}
                </div>
                """
                folium.Marker(
                    location=[float(row['Latitude']), float(row['Longitude'])],
                    popup=folium.Popup(popup_content, max_width=250),
                    tooltip=row['Nama Tempat']
                ).add_to(marker_cluster)
                
            st_folium(m, width="100%", height=500)
        else:
            pd_st.warning("Tidak dapat memetakan lokasi karena tidak ada data Latitude & Longitude presisi yang ditemukan dari hasil pencarian saat ini.")

else:
    pd_st.info("💡 Selamat datang di MarketSpy! Silakan tentukan kata kunci pencarian Anda pada menu sidebar kiri lalu klik tombol **'Mulai Scrape Data'** untuk mengumpulkan data prospek bisnis.")
