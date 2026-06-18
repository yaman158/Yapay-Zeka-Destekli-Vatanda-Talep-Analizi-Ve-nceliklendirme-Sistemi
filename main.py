import imaplib
import email
import re
from email.header import decode_header
import sqlite3
import json
import time
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ==========================================
# 1. AYARLAR VE KİMLİK BİLGİLERİ
# ==========================================
DB_NAME = r"D:\Yaman\Python\pythonProject12\telekom.db"

# E-posta Ayarları
EMAIL_ADRESI = "kamalfamily1999@gmail.com"
UYGULAMA_SIFRESI = "mbpg eeub qimc cypi"
IMAP_SUNUCUSU = "imap.gmail.com"
HEDEF_GONDEREN = "ykf20002@gmail.com"

# OpenClaw Ayarları
client = OpenAI(
    base_url="http://127.0.0.1:18789/v1",
    api_key="e63ac38b96032cddac0527b478ee63bb0f6104f20efe6657"
)


# ==========================================
# 2. VERİTABANI VE ŞALTER KONTROLÜ
# ==========================================
def yapay_zeka_aktif_mi():
    """Web Admin panelindeki o büyük AI şalterinin durumunu kontrol eder."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # YENİ SORGUMUZ: Anahtar'ı 'YapayZekaAktif' olan satırın 'Deger'ini getir
        cursor.execute("SELECT Deger FROM SistemAyarlari WHERE Anahtar = 'YapayZekaAktif'")
        sonuc = cursor.fetchone()
        conn.close()

        if sonuc:
            # Artık veritabanında metin (TEXT) olarak "1" veya "0" tuttuğumuz için buna göre kontrol ediyoruz
            return sonuc[0] == "1"

        return True  # Eğer tablo boşsa mecburen çalışsın

    except Exception as e:
        print(f"⚠️ [SİSTEM UYARISI] Yapay Zeka şalteri okunamadı: {e}")
        conn.close()
        return True  # Tablo hata verirse güvenlik önlemi olarak çalışmaya devam etsin


# ==========================================
# 3. MAİLLERİ İNDİRME MOTORU (POSTACI)
# ==========================================
def mailleri_cek():
    """Gmail'e bağlanıp yeni mailleri veya müşteri yanıtlarını veritabanına işler."""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SUNUCUSU)
        mail.login(EMAIL_ADRESI, UYGULAMA_SIFRESI)
        mail.select("inbox")

        status, messages = mail.search(None, 'UNSEEN', 'FROM', f'"{HEDEF_GONDEREN}"')
        mail_id_list = messages[0].split()

        if not mail_id_list:
            mail.logout()
            return  # Yeni mail yoksa sessizce çık

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        for mail_id in mail_id_list:
            res, msg_data = mail.fetch(mail_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    # Konu ve Gönderen
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                    sender = msg.get("From")

                    # İçerik
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                    # ========================================================
                    # AKILLI KONTROL VE KAYIT BÖLÜMÜ (YENİ EKLENEN KISIM)
                    # ========================================================

                    # 1. Gelen maili geçmiş alıntılardan (>, On ... wrote) temizle
                    temiz_icerik = mail_metnini_temizle(body)

                    # 2. Konuda "(Talep #23)" gibi bir ID var mı kontrol et (Regex)
                    match = re.search(r'\(Talep #(\d+)\)', subject)

                    if match:
                        # AHA! Bu eski bir talebe gelen cevap (Reply)
                        talep_id = int(match.group(1))
                        print(f"🔄 [MÜŞTERİ YANITI] Talep #{talep_id} için yeni mesaj geldi.")

                        # Mesajlar tablosuna "Müşteri" mesajı olarak ekle
                        cursor.execute("""
                            INSERT INTO Mesajlar (MailId, GonderenTip, Mesaj) 
                            VALUES (?, 'Müşteri', ?)
                        """, (talep_id, temiz_icerik))

                        # Personelin ekranında uyarılması için ana mailin durumunu değiştir
                        cursor.execute("""
                            UPDATE GelenMailler SET Durum = 'Müşteri Yanıtladı' 
                            WHERE Id = ?
                        """, (talep_id,))

                    else:
                        # BU YEPYENİ BİR ŞİKAYET!
                        print(f"🆕 [YENİ ŞİKAYET] Konu: {subject}")

                        # GelenMailler tablosuna yepyeni bir kayıt olarak aç (Yapay Zeka departman atayacak)
                        cursor.execute("""
                            INSERT INTO GelenMailler (Gonderen, Konu, Icerik, Durum)
                            VALUES (?, ?, ?, 'Bekliyor')
                        """, (sender, subject, temiz_icerik))

        conn.commit()
        conn.close()
        mail.logout()

    except Exception as e:
        print(f"❌ [HATA] Mail çekerken bir sorun oluştu: {e}")


def mail_metnini_temizle(metin):
    """Müşterinin yanıtından eski maillerin alıntılarını (>, On Date wrote vs.) temizler."""
    satirlar = metin.splitlines()
    temiz_satirlar = []

    for satir in satirlar:
        satir_strip = satir.strip()

        # Alıntı işaretleri (>) veya sistemin kendi imzasına (---) gelirsek okumayı kes
        if satir_strip.startswith('>') or "---" in satir_strip or "Yanıtlamak için bu maili" in satir_strip:
            break

        # Gmail tarih/yazdı formatları (İngilizce 'On ... wrote:' ve Türkçe 'tarihinde ... yazdı:')
        if (satir_strip.startswith('On ') and 'wrote:' in satir_strip) or (
                'tarihinde' in satir_strip and 'yazdı' in satir_strip):
            break

        temiz_satirlar.append(satir)

    return '\n'.join(temiz_satirlar).strip()

# ==========================================
# 4. YAPAY ZEKA (BEYİN) MOTORU
# ==========================================
def openclaw_karar_iste(konu, icerik):
    """OpenClaw üzerinden Gemini'a bağlanır ve JSON kararı alır."""
    try:
        with open("SOUL.md", "r", encoding="utf-8") as file:
            sistem_kurallari = file.read()
    except:
        sistem_kurallari = "Sen bir yönlendirme asistanısın. Sadece JSON formatında 'yonlendirilen_departman' ve 'aciliyet' değerlerini dön."

    try:
        response = client.chat.completions.create(
            model="gemini/gemini-1.5-flash",
            messages=[
                {"role": "system", "content": sistem_kurallari},
                {"role": "user", "content": f"Konu: {konu}\nİçerik: {icerik}"}
            ],
            temperature=0.1
        )
        ai_cevabi = response.choices[0].message.content
        ai_cevabi = ai_cevabi.replace("```json", "").replace("```", "").strip()

        try:
            return json.loads(ai_cevabi)
        except json.JSONDecodeError:
            print("❌ [HATA] Yapay Zeka JSON formatında cevap vermedi.")
            return {"yonlendirilen_departman": "Belirsiz", "aciliyet": "Orta"}

    except Exception as e:
        print(f"❌ [HATA] Yapay Zeka ile iletişim kurulamadı: {e}")
        return {"yonlendirilen_departman": "Bağlantı Hatası", "aciliyet": "Yüksek"}


def mailleri_isle():
    """Veritabanındaki 'Bekliyor' maillerini okur ve yapay zekaya işletir."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT Id, Gonderen, Konu, Icerik FROM GelenMailler WHERE Durum = 'Bekliyor' LIMIT 1")
    bekleyen_mail = cursor.fetchone()

    if bekleyen_mail:
        mail_id, gonderen, konu, icerik = bekleyen_mail
        print(f"🧠 [YAPAY ZEKA] ID: {mail_id} inceleniyor...")

        # Kararı Al
        karar = openclaw_karar_iste(konu, icerik)
        departman = karar.get("yonlendirilen_departman", "Bilinmiyor")
        aciliyet = karar.get("aciliyet", "Bilinmiyor")

        # Kararı İkinci Tabloya Yaz
        cursor.execute("""
            INSERT INTO YonlendirilenMailler (MailId, Departman, Aciliyet, IletimDurumu)
            VALUES (?, ?, ?, 'Yapay Zeka Yönlendirdi')
        """, (mail_id, departman, aciliyet))

        # Ana Tablodaki Durumu C# paneliyle uyumlu olması için 'Yönlendirildi' yap
        cursor.execute("UPDATE GelenMailler SET Durum = 'Yönlendirildi' WHERE Id = ?", (mail_id,))

        conn.commit()
        print(f"✅ [İŞLEM TAMAM] Mail '{departman}' departmanına '{aciliyet}' aciliyetiyle atandı.\n")

    conn.close()


# ==========================================
# 4.5 POSTACI (SMTP) MOTORU - CEVAPLARI GÖNDERME
# ==========================================
def mesajlari_gonder():
    """Mesajlar tablosundaki gönderilmemiş personel mesajlarını iletir."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # SADECE personelin yazdığı ve henüz iletilmemiş (0) mesajları çekiyoruz
    cursor.execute("""
        SELECT ms.Id as MesajID, ms.MailId, ms.Mesaj, m.Gonderen, m.Konu
        FROM Mesajlar ms
        JOIN GelenMailler m ON ms.MailId = m.Id
        WHERE ms.GonderenTip = 'Personel' AND ms.IletildiMi = 0
    """)
    bekleyenler = cursor.fetchall()

    if not bekleyenler:
        conn.close()
        return

    try:
        # SMTP Bağlantısını Başlat
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_ADRESI, UYGULAMA_SIFRESI)

        for satir in bekleyenler:
            m_id = satir['MailId']
            hedef_mail = satir['Gonderen']
            konu = satir['Konu']
            mesaj_metni = satir['Mesaj']
            mesaj_id = satir['MesajID']

            print(f"📤 [POSTACI] Talep #{m_id} için yeni mesaj gönderiliyor...")

            # Mail Paketini Hazırla
            msg = MIMEMultipart()
            msg['From'] = f"Telekom Destek <{EMAIL_ADRESI}>"
            msg['To'] = hedef_mail
            # KONU ÇOK ÖNEMLİ: Müşteri reply yaptığında #ID'yi buradan okuyacağız
            msg['Subject'] = f"RE: {konu} (Talep #{m_id})"

            govde = f"{mesaj_metni}\n\n---\nYanıtlamak için bu maili bozmadan cevaplayın. (Talep #{m_id})"
            msg.attach(MIMEText(govde, 'plain', 'utf-8'))

            # Gönder!
            server.send_message(msg)

            # BAŞARILI: Veritabanında 'İletildi' olarak işaretle
            cursor.execute("UPDATE Mesajlar SET IletildiMi = 1 WHERE Id = ?", (mesaj_id,))
            conn.commit()
            print(f"✅ Mesaj başarıyla iletildi (ID: {mesaj_id})")

        server.quit()
    except Exception as e:
        print(f"❌ [SMTP HATASI] Mesajlar gönderilemedi: {e}")
    finally:
        conn.close()

# ==========================================
# 5. ANA DÖNGÜ (SİSTEMİN KALP ATIŞI)
# ==========================================
def ajani_baslat():
    print("🚀 Sistem Başlatıldı! Otonom Ajan devrede...\n")
    print("Masaüstü Admin panelindeki kırmızı butona basarak beni durdurabilirsiniz.\n")
    print("-" * 50)

    while True:
        if yapay_zeka_aktif_mi():
            mailleri_cek()  # Önce mail var mı diye posta kutusuna bak
            mailleri_isle()  # Sonra veritabanına inip AI ile işle
            mesajlari_gonder()  # 3. YENİ: Personelin yazdığı cevapları müşteriye yolla!
        else:
            # Şalter indirilmişse sessizce bekle
            print("🚨 [SİSTEM DURDURULDU] Admin şalteri indirdi. Uyku modundayım...", end="\r")

        # Sunucuları yormamak için her tur arası 5 saniye bekle
        time.sleep(5)


if __name__ == "__main__":
    ajani_baslat()