from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import io
import csv
from flask import make_response

app = Flask(__name__)
app.secret_key = "cok_gizli_anahtar_123"  # Güvenlik oturumları için şart
DB_PATH = r"D:\Yaman\Python\pythonProject12\telekom.db"


# --- YARDIMCI FONKSİYON ---
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ==========================================
# 1. GİRİŞ (LOGIN) ROTASI
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        kullanici = request.form['kullanici']
        sifre = request.form['sifre']

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM Kullanicilar WHERE KullaniciAdi = ? AND Sifre = ?",
                            (kullanici, sifre)).fetchone()
        conn.close()

        if user:
            session['logged_in'] = True
            session['user'] = user['KullaniciAdi']
            session['rol'] = user['Rol']
            session['departman'] = user['Departman']

            # DÜZELTME: Artık herkesi ortak ana kapıya yönlendiriyoruz!
            return redirect(url_for('ana_sayfa'))
        else:
            return render_template('login.html', hata="Hatalı kullanıcı adı veya şifre!")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()  # Kimlik kartını yırt at
    return redirect(url_for('login'))


# ==========================================
# 2. ORTAK ANA SAYFA (DASHBOARD) KAPISI
# ==========================================
@app.route('/')
def ana_sayfa():
    # Güvenlik: Giriş yapılmamışsa Login'e at
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # KONTROL: Giren kişi Admin mi, Personel mi?
    if session.get('rol') == 'Admin':
        stats = {
            "toplam": cursor.execute("SELECT COUNT(*) FROM GelenMailler").fetchone()[0],
            "bekleyen": cursor.execute("SELECT COUNT(*) FROM GelenMailler WHERE Durum = 'Bekliyor'").fetchone()[0],
            "yonlendirilen":
                cursor.execute("SELECT COUNT(*) FROM GelenMailler WHERE Durum = 'Yönlendirildi'").fetchone()[0],
            "cozuldu": cursor.execute("SELECT COUNT(*) FROM GelenMailler WHERE Durum = 'Çözüldü'").fetchone()[0],
        }

        # --- YENİ EKLENEN AI DURUM KONTROLÜ ---
        # Veritabanında SistemAyarlari tablosu yoksa veya boşsa çökmemesi için güvenlik önlemi
        ai_durum_sorgu = cursor.execute("SELECT Deger FROM SistemAyarlari WHERE Anahtar = 'YapayZekaAktif'").fetchone()
        ai_durum = ai_durum_sorgu[0] if ai_durum_sorgu else "0"

        conn.close()
        return render_template('admin_dashboard.html', stats=stats, ai_durum=ai_durum)

    else:  # Eğer Admin değilse kesin personeldir
        dept = session.get('departman')
        stats = {
            "bekleyen": cursor.execute("""
                SELECT COUNT(*) FROM GelenMailler m 
                JOIN YonlendirilenMailler y ON m.Id = y.MailId 
                WHERE y.Departman = ? AND m.Durum = 'Yönlendirildi'""", (dept,)).fetchone()[0],
            "cozuldu": cursor.execute("""
                SELECT COUNT(*) FROM GelenMailler m 
                JOIN YonlendirilenMailler y ON m.Id = y.MailId 
                WHERE y.Departman = ? AND m.Durum = 'Çözüldü'""", (dept,)).fetchone()[0],
        }
        conn.close()
        return render_template('personel_dashboard.html', stats=stats)


# ==========================================
# 2.1 ADMİN: AI ŞALTERİNİ DEĞİŞTİR (ON/OFF)
# ==========================================
@app.route('/ai_toggle', methods=['POST'])
def ai_toggle():
    # Güvenlik: Sadece Adminler bu şalterle oynayabilir
    if 'logged_in' not in session or session.get('rol') != 'Admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    # Mevcut durumu oku
    mevcut_durum = conn.execute("SELECT Deger FROM SistemAyarlari WHERE Anahtar = 'YapayZekaAktif'").fetchone()[0]

    # Durumu tersine çevir (1 ise 0, 0 ise 1 yap)
    yeni_durum = "0" if mevcut_durum == "1" else "1"

    # Yeni durumu veritabanına kaydet
    conn.execute("UPDATE SistemAyarlari SET Deger = ? WHERE Anahtar = 'YapayZekaAktif'", (yeni_durum,))
    conn.commit()
    conn.close()

    # İşlem bitince ana sayfaya geri dön
    return redirect(url_for('ana_sayfa'))


# ==========================================
# 2.5 ADMİN: TÜM İŞLER TABLOSU (/isler)
# ==========================================
@app.route('/isler')
def isler_sayfasi():
    # Güvenlik: Admin değilse giremesin!
    if 'logged_in' not in session or session.get('rol') != 'Admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    # Tüm mailleri ve yapay zeka kararlarını çekiyoruz
    mailler = conn.execute("""
        SELECT m.Id, m.Gonderen, m.Konu, y.Departman, y.Aciliyet, m.Durum
        FROM GelenMailler m
        LEFT JOIN YonlendirilenMailler y ON m.Id = y.MailId
        ORDER BY m.Id DESC
    """).fetchall()
    conn.close()

    return render_template('isler.html', isler=mailler)


# ==========================================
# 3. PERSONEL EKRANI (MÜŞTERİ HİZMETLERİ)
# ==========================================
@app.route('/islerim')
def personel_paneli():
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    # 1. Sol Menü İçin: Sadece Açık Talepleri Getir
    mailler = conn.execute("""
        SELECT m.Id, m.Gonderen, m.Konu, y.Aciliyet, m.Durum, m.GelisTarihi
        FROM GelenMailler m
        JOIN YonlendirilenMailler y ON m.Id = y.MailId
        WHERE y.Departman = ? AND m.Durum != 'Çözüldü'
        ORDER BY m.Id DESC
    """, (session['departman'],)).fetchall()

    # Seçili bir mail varsa detaylarını, mesaj geçmişini ve müşteri geçmişini al
    secili_mail_id = request.args.get('secili_id')
    secili_detay = None
    mesajlar = []
    musteri_gecmisi = []

    if secili_mail_id:
        secili_detay = conn.execute("SELECT * FROM GelenMailler WHERE Id = ?", (secili_mail_id,)).fetchone()

        # Bu talebe ait SOHBET geçmişini çek
        mesajlar = conn.execute("SELECT * FROM Mesajlar WHERE MailId = ? ORDER BY Tarih ASC",
                                (secili_mail_id,)).fetchall()

        # Müşterinin ESKİ TALEPLERİNİ çek (Departman fark etmeksizin)
        musteri_gecmisi = conn.execute("""
            SELECT Id, Konu, Durum, GelisTarihi 
            FROM GelenMailler 
            WHERE Gonderen = ? AND Id != ? 
            ORDER BY Id DESC LIMIT 5
        """, (secili_detay['Gonderen'], secili_mail_id)).fetchall()

    conn.close()

    return render_template('personel_cevap.html', mailler=mailler, secili_detay=secili_detay, mesajlar=mesajlar,
                           musteri_gecmisi=musteri_gecmisi)



@app.route('/sifre_degistir', methods=['GET', 'POST'])
def sifre_degistir():
    # Sadece giriş yapmış kullanıcılar girebilir
    if 'kullanici' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        eski_sifre = request.form.get('eski_sifre')
        yeni_sifre = request.form.get('yeni_sifre')
        tekrar_sifre = request.form.get('tekrar_sifre')
        kullanici = session['kullanici']

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Veritabanından mevcut şifreyi çek
        user = cursor.execute("SELECT Sifre FROM Kullanicilar WHERE Id = ?", (kullanici_id,)).fetchone()

        # Güvenlik kontrolleri
        if user['Sifre'] != eski_sifre:
            return render_template('sifre_degistir.html', hata="Mevcut şifrenizi yanlış girdiniz.")
        elif yeni_sifre != tekrar_sifre:
            return render_template('sifre_degistir.html', hata="Yeni girdiğiniz şifreler birbiriyle eşleşmiyor.")
        else:
            # Şifreyi güncelle
            cursor.execute("UPDATE Kullanicilar SET Sifre = ? WHERE Id = ?", (yeni_sifre, kullanici_id))
            conn.commit()
            conn.close()
            # Başarılı olursa kendi paneline geri gönder
            return redirect(url_for('personel_dashboard')) 

    return render_template('sifre_degistir.html')
#kötü
@app.route('/arsiv')
def arsiv_sayfasi():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # SİHİR BURADA: Durumu Çözüldü olan ve geliş tarihi şu andan 3 gün veya daha eski olanları çek
    arsiv_mailler = conn.execute("""
        SELECT * FROM YonlendirilenMailler 
        WHERE IletimDurumu = 'Çözüldü' AND IslemTarihi <= datetime('now', '-3 days') 
        ORDER BY IslemTarihi DESC
    """).fetchall()
    
    conn.close()
    return render_template('arsiv.html', mailler=arsiv_mailler)


# ==========================================
# 4. CEVAP GÖNDERME VE KAPATMA AKSİYONLARI
# ==========================================
@app.route('/islem_yap/<int:mail_id>', methods=['POST'])
def islem_yap(mail_id):
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    aksiyon = request.form['aksiyon']  # Hangi butona basıldı? (cevapla veya kapat)
    yeni_mesaj = request.form.get('cevap', '').strip()

    conn = get_db_connection()

    # Eğer kutuya bir şeyler yazıldıysa, bunu yeni mesaj olarak ekle
    if yeni_mesaj:
        conn.execute("INSERT INTO Mesajlar (MailId, GonderenTip, Mesaj) VALUES (?, 'Personel', ?)",
                     (mail_id, yeni_mesaj))

    # Butona göre durumu değiştir
    if aksiyon == 'cevapla':
        # Sadece cevapla dediyse, durumu 'Müşteri Yanıtı Bekleniyor' yap
        conn.execute("UPDATE GelenMailler SET Durum = 'Müşteri Yanıtı Bekleniyor' WHERE Id = ?", (mail_id,))

    elif aksiyon == 'kapat':
        # Çözüldü deyip kapattıysa
        conn.execute("UPDATE GelenMailler SET Durum = 'Çözüldü' WHERE Id = ?", (mail_id,))

    conn.commit()
    conn.close()

    # İşlem bitince aynı mailin ekranında kal
    return redirect(url_for('personel_paneli', secili_id=mail_id))

# ==========================================
# 5. ÇÖZÜLEN İŞLER GEÇMİŞİ (PERSONEL İÇİN)
# ==========================================
@app.route('/cozulenler')
def cozulenler_sayfasi():
    # Güvenlik: Giriş yapmamışsa veya Admin buraya girmeye çalışırsa engelle
    if 'logged_in' not in session or session.get('rol') == 'Admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    # Sadece giriş yapan personelin departmanındaki "Çözüldü" olan işleri getir
    cozulen_mailler = conn.execute("""
        SELECT m.Id, m.Gonderen, m.Konu, y.Aciliyet, m.Durum
        FROM GelenMailler m
        JOIN YonlendirilenMailler y ON m.Id = y.MailId
        WHERE y.Departman = ? AND m.Durum = 'Çözüldü'
        ORDER BY m.Id DESC
    """, (session['departman'],)).fetchall()
    conn.close()

    return render_template('cozulenler.html', mailler=cozulen_mailler)

#excel
@app.route('/personel_rapor/<int:personel_id>')
def personel_rapor(personel_id):
    # Güvenlik kontrolü
    if session.get('rol') != 'Admin':
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Personelin adını al
    personel = cursor.execute("SELECT KullaniciAdi FROM Kullanicilar WHERE Id = ?", (personel_id,)).fetchone()
    if not personel:
        return "Personel bulunamadı", 404
    
    p_adi = personel['KullaniciAdi']

    # DİKKAT: Veritabanında işi çözen personeli hangi kolonda tutuyorsan (örn: Sorumlu, Cevaplayan, Personel vs.)
    # aşağıdaki 'Cevaplayan = ?' kısmını kendi sistemine göre güncelle.
    cursor.execute("SELECT Id, MailId, Departman, IslemTarihi FROM YonlendirilenMailler WHERE IletimDurumu = 'Çözüldü' AND Cevaplayan = ?", (p_adi,))
    isler = cursor.fetchall()
    conn.close()

    # CSV dosyasını bellekte oluştur
    si = io.StringIO()
    # Türkçe karakter sorunu (Ş, Ğ, İ) yaşanmaması için BOM (Byte Order Mark) ekliyoruz
    si.write('\ufeff')
    cw = csv.writer(si, delimiter=';') # Excel hücreleri ayırmak için noktalı virgül sever
    
    # Excel Başlıkları
    cw.writerow(['Talep ID', 'Müşteri Maili', 'Konu', 'Çözüm Tarihi'])
    
    # Verileri Satır Satır Yaz
    for is_ in isler:
        cw.writerow([is_['Id'], is_['Gonderen'], is_['Konu'], is_['IslemTarihi']])

    # Dosyayı kullanıcıya indirt
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={p_adi}_Aylik_Rapor.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    
    return output

# ==========================================
# 6. PERSONEL YÖNETİMİ (CRUD İŞLEMLERİ)
# ==========================================

# 6.1: Personel Listesini Görüntüleme
@app.route('/personel_yonetimi')
def personel_yonetimi():
    if 'logged_in' not in session or session.get('rol') != 'Admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    # Tüm kullanıcıları çekiyoruz (Adminler en üstte görünsün diye Rol'e göre sıraladık)
    personeller = conn.execute("SELECT * FROM Kullanicilar ORDER BY Rol, KullaniciAdi").fetchall()
    conn.close()

    return render_template('personel_yonetimi.html', personeller=personeller)


# 6.2: Yeni Personel Ekleme
@app.route('/personel_ekle', methods=['POST'])
def personel_ekle():
    if 'logged_in' not in session or session.get('rol') != 'Admin':
        return redirect(url_for('login'))

    k_adi = request.form['kullanici_adi']
    sifre = request.form['sifre']
    rol = request.form['rol']
    departman = request.form['departman']

    conn = get_db_connection()
    conn.execute("INSERT INTO Kullanicilar (KullaniciAdi, Sifre, Rol, Departman) VALUES (?, ?, ?, ?)",
                 (k_adi, sifre, rol, departman))
    conn.commit()
    conn.close()

    return redirect(url_for('personel_yonetimi'))


# 6.3: Personel Düzenleme (Departman/Şifre Değiştirme)
@app.route('/personel_duzenle/<int:id>', methods=['POST'])
def personel_duzenle(id):
    if 'logged_in' not in session or session.get('rol') != 'Admin':
        return redirect(url_for('login'))

    departman = request.form['departman']
    rol = request.form['rol']
    yeni_sifre = request.form.get('sifre', '').strip()

    conn = get_db_connection()

    # Eğer şifre kutusu boş bırakılmadıysa şifreyi de güncelle
    if yeni_sifre:
        conn.execute("UPDATE Kullanicilar SET Departman = ?, Rol = ?, Sifre = ? WHERE Id = ?",
                     (departman, rol, yeni_sifre, id))
    else:
        conn.execute("UPDATE Kullanicilar SET Departman = ?, Rol = ? WHERE Id = ?",
                     (departman, rol, id))

    conn.commit()
    conn.close()

    return redirect(url_for('personel_yonetimi'))


# 6.4: Personel Silme
@app.route('/personel_sil/<int:id>', methods=['POST'])
def personel_sil(id):
    if 'logged_in' not in session or session.get('rol') != 'Admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    conn.execute("DELETE FROM Kullanicilar WHERE Id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for('personel_yonetimi'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)